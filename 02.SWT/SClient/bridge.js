const fs = require('fs');
const path = require('path');
const https = require('https');
const { WebSocketServer } = require('ws');
const pcsclite = require('@pokusew/pcsclite');

const SECURE = process.env.SECURE === '1' || process.env.SECURE === 'true';
const WS_PORT = parseInt(process.env.BRIDGE_PORT || (SECURE ? '8444' : '8081'), 10);
const SWEB_PORT = process.env.SWEB_PORT || (SECURE ? '8443' : '8080');
const DEFAULT_ORIGIN = `${SECURE ? 'https' : 'http'}://localhost:${SWEB_PORT}`;
const ALLOWED_ORIGINS = (process.env.ALLOWED_ORIGINS || DEFAULT_ORIGIN)
  .split(',').map(s => s.trim()).filter(Boolean);

function verifyOrigin(origin) {
  if (!origin) return !SECURE;
  return ALLOWED_ORIGINS.includes(origin);
}

function verifyClient(info, cb) {
  const origin = info.origin || info.req.headers.origin || '';
  if (verifyOrigin(origin)) return cb(true);
  console.warn(`[Bridge] origin rejected: "${origin}"`);
  cb(false, 403, 'origin not allowed');
}

const readers = new Map();

const session = {
  name: null,
  protocol: null
};

const pcsc = pcsclite();
let wss = null;

function broadcast(obj) {
  if (!wss) return;
  const msg = JSON.stringify(obj);
  for (const client of wss.clients) {
    if (client.readyState === 1) client.send(msg);
  }
}

function readersSnapshot() {
  return Array.from(readers.entries()).map(([name, info]) => ({
    name,
    hasCard: !!info.hasCard,
    atr: info.atr || null,
    connected: session.name === name
  }));
}

function pushReaders() {
  broadcast({ type: 'READERS', readers: readersSnapshot() });
}

pcsc.on('reader', (reader) => {
  console.log(`[PC/SC] reader detected: ${reader.name}`);
  readers.set(reader.name, { reader, hasCard: false, atr: null });
  pushReaders();

  reader.on('error', (err) => {
    console.error(`[PC/SC] reader error (${reader.name}): ${err.message}`);
  });

  reader.on('status', (status) => {
    const info = readers.get(reader.name);
    if (!info) return;
    const changes = reader.state ^ status.state;
    if (!changes) return;

    if ((changes & reader.SCARD_STATE_EMPTY) && (status.state & reader.SCARD_STATE_EMPTY)) {
      console.log(`[PC/SC] card removed from ${reader.name}`);
      info.hasCard = false;
      info.atr = null;
      if (session.name === reader.name) {
        reader.disconnect(reader.SCARD_LEAVE_CARD, () => {});
        session.name = null;
        session.protocol = null;
      }
      pushReaders();
    } else if ((changes & reader.SCARD_STATE_PRESENT) && (status.state & reader.SCARD_STATE_PRESENT)) {
      info.hasCard = true;
      if (status.atr && status.atr.length) {
        info.atr = Buffer.from(status.atr).toString('hex').toUpperCase();
      }
      console.log(`[PC/SC] card present on ${reader.name}, ATR=${info.atr || 'n/a'}`);
      pushReaders();
    }
  });

  reader.on('end', () => {
    console.log(`[PC/SC] reader removed: ${reader.name}`);
    if (session.name === reader.name) {
      session.name = null;
      session.protocol = null;
    }
    readers.delete(reader.name);
    pushReaders();
  });
});

pcsc.on('error', (err) => {
  console.error(`[PC/SC] service error: ${err.message}`);
});

function pickName(requested) {
  if (requested && readers.has(requested)) return requested;
  if (session.name && readers.has(session.name)) return session.name;
  const first = readers.keys().next().value;
  return first || null;
}

function connectReader(name, share = 'shared') {
  return new Promise((resolve, reject) => {
    const info = readers.get(name);
    if (!info) return reject(new Error(`리더기를 찾을 수 없습니다: ${name}`));
    const reader = info.reader;
    const shareMode = share === 'exclusive'
      ? reader.SCARD_SHARE_EXCLUSIVE
      : reader.SCARD_SHARE_SHARED;
    const protos = reader.SCARD_PROTOCOL_T0 | reader.SCARD_PROTOCOL_T1;

    reader.connect({ share_mode: shareMode, protocol: protos }, (err, protocol) => {
      if (err) return reject(err);
      const proto = typeof protocol === 'number' ? protocol : reader.SCARD_PROTOCOL_T0;
      session.name = name;
      session.protocol = proto;
      console.log(`[PC/SC] connected: ${name}, protocol=${proto}`);
      pushReaders();
      resolve({ reader: name, atr: info.atr, protocol: proto });
    });
  });
}

async function coldResetReader(name) {
  const info = readers.get(name);
  if (!info) throw new Error(`리더기를 찾을 수 없습니다: ${name}`);
  const reader = info.reader;

  if (session.name && session.name !== name) {
    const other = readers.get(session.name);
    if (other) {
      await new Promise((res) => other.reader.disconnect(other.reader.SCARD_LEAVE_CARD, () => res()));
    }
    session.name = null;
    session.protocol = null;
  }

  if (session.name !== name) {
    await new Promise((res, rej) => {
      const protos = reader.SCARD_PROTOCOL_T0 | reader.SCARD_PROTOCOL_T1;
      reader.connect({ share_mode: reader.SCARD_SHARE_SHARED, protocol: protos }, (err, proto) => {
        if (err) return rej(err);
        session.name = name;
        session.protocol = typeof proto === 'number' ? proto : reader.SCARD_PROTOCOL_T0;
        res();
      });
    });
  }

  await new Promise((res, rej) => {
    reader.disconnect(reader.SCARD_UNPOWER_CARD, (err) => err ? rej(err) : res());
  });
  console.log(`[PC/SC] cold reset: power cycled on ${name}`);
  session.name = null;
  session.protocol = null;

  const result = await connectReader(name);
  console.log(`[PC/SC] cold reset done on ${name}, ATR=${result.atr || 'n/a'}`);
  return result;
}

function warmResetReader() {
  return new Promise((resolve, reject) => {
    if (!session.name) return reject(new Error('연결된 리더기가 없습니다. 먼저 연결하세요.'));
    const info = readers.get(session.name);
    if (!info) return reject(new Error('세션 리더가 더 이상 존재하지 않습니다.'));
    const reader = info.reader;
    const name = session.name;
    const protos = reader.SCARD_PROTOCOL_T0 | reader.SCARD_PROTOCOL_T1;

    reader.disconnect(reader.SCARD_RESET_CARD, (err) => {
      if (err) return reject(err);
      reader.connect({ share_mode: reader.SCARD_SHARE_SHARED, protocol: protos }, (err2, protocol) => {
        if (err2) {
          session.name = null;
          session.protocol = null;
          pushReaders();
          return reject(err2);
        }
        const proto = typeof protocol === 'number' ? protocol : reader.SCARD_PROTOCOL_T0;
        session.protocol = proto;
        console.log(`[PC/SC] warm reset done on ${name}, protocol=${proto}`);
        pushReaders();
        resolve({ reader: name, atr: info.atr, protocol: proto });
      });
    });
  });
}

function disconnectReader() {
  return new Promise((resolve, reject) => {
    if (!session.name) return resolve({ reader: null });
    const info = readers.get(session.name);
    const name = session.name;
    if (!info) {
      session.name = null;
      session.protocol = null;
      return resolve({ reader: name });
    }
    info.reader.disconnect(info.reader.SCARD_LEAVE_CARD, (err) => {
      if (err) return reject(err);
      console.log(`[PC/SC] disconnected: ${name}`);
      session.name = null;
      session.protocol = null;
      pushReaders();
      resolve({ reader: name });
    });
  });
}

function transmitApdu(hex) {
  return new Promise((resolve, reject) => {
    if (!session.name) return reject(new Error('카드가 연결되어 있지 않습니다. 먼저 연결하세요.'));
    const info = readers.get(session.name);
    if (!info) return reject(new Error('세션 리더가 더 이상 존재하지 않습니다.'));
    const cmd = Buffer.from(hex, 'hex');
    info.reader.transmit(cmd, 512, session.protocol, (err, data) => {
      if (err) return reject(err);
      const respHex = data.toString('hex').toUpperCase();
      const sw = respHex.slice(-4);
      const body = respHex.slice(0, -4);
      resolve({ response: respHex, body, sw });
    });
  });
}

if (SECURE) {
  const certDir = path.resolve(__dirname, '..', 'certs');
  const keyPath = path.join(certDir, 'server.key');
  const crtPath = path.join(certDir, 'server.crt');
  if (!fs.existsSync(keyPath) || !fs.existsSync(crtPath)) {
    console.error(`[Bridge] 인증서 없음: ${certDir}\n먼저 "node gen-cert.js"를 실행하세요.`);
    process.exit(1);
  }
  const server = https.createServer({
    key: fs.readFileSync(keyPath),
    cert: fs.readFileSync(crtPath)
  });
  wss = new WebSocketServer({ server, verifyClient });
  server.listen(WS_PORT, () => {
    console.log(`[Bridge] WSS listening on wss://localhost:${WS_PORT}`);
    console.log(`[Bridge] allowed origins: ${ALLOWED_ORIGINS.join(', ')}`);
  });
} else {
  wss = new WebSocketServer({ port: WS_PORT, verifyClient });
  console.log(`[Bridge] WS listening on ws://localhost:${WS_PORT}`);
  console.log(`[Bridge] allowed origins: ${ALLOWED_ORIGINS.join(', ')}`);
}

wss.on('connection', (ws) => {
  console.log('[Bridge] client connected');
  ws.send(JSON.stringify({ type: 'READERS', readers: readersSnapshot() }));

  ws.on('message', async (raw) => {
    let msg;
    try {
      msg = JSON.parse(raw.toString());
    } catch {
      return ws.send(JSON.stringify({ type: 'ERROR', message: 'invalid JSON' }));
    }

    try {
      switch (msg.action) {
        case 'LIST_READERS': {
          ws.send(JSON.stringify({ type: 'READERS', readers: readersSnapshot() }));
          break;
        }
        case 'CONNECT': {
          const name = pickName(msg.reader);
          if (!name) throw new Error('연결 가능한 리더기가 없습니다.');
          const r = await connectReader(name, msg.share);
          ws.send(JSON.stringify({ type: 'CONNECT_OK', ...r }));
          break;
        }
        case 'DISCONNECT': {
          const r = await disconnectReader();
          ws.send(JSON.stringify({ type: 'DISCONNECT_OK', ...r }));
          break;
        }
        case 'WARM_RESET': {
          const r = await warmResetReader();
          ws.send(JSON.stringify({ type: 'WARM_RESET_OK', ...r }));
          break;
        }
        case 'RESET':
        case 'COLD_RESET': {
          const name = pickName(msg.reader);
          if (!name) throw new Error('연결 가능한 리더기가 없습니다.');
          const r = await coldResetReader(name);
          ws.send(JSON.stringify({ type: 'COLD_RESET_OK', reader: r.reader, atr: r.atr }));
          break;
        }
        case 'TRANSMIT': {
          if (typeof msg.apdu !== 'string') throw new Error('apdu (hex string) 필드가 필요합니다.');
          const result = await transmitApdu(msg.apdu);
          ws.send(JSON.stringify({ type: 'TRANSMIT_OK', ...result }));
          break;
        }
        default:
          ws.send(JSON.stringify({ type: 'ERROR', message: `unknown action: ${msg.action}` }));
      }
    } catch (err) {
      console.error(`[Bridge] action error: ${err.message}`);
      ws.send(JSON.stringify({ type: 'ERROR', message: err.message }));
    }
  });

  ws.on('close', () => console.log('[Bridge] client disconnected'));
});

process.on('SIGINT', () => {
  console.log('\n[Bridge] shutting down...');
  wss.close();
  if (session.name) {
    const info = readers.get(session.name);
    if (info) {
      info.reader.disconnect(info.reader.SCARD_LEAVE_CARD, () => process.exit(0));
      return;
    }
  }
  process.exit(0);
});
