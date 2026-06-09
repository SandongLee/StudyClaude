const { WebSocketServer } = require('ws');
const pcsclite = require('@pokusew/pcsclite');

const WS_PORT = 8081;

const state = {
  readerName: null,
  reader: null,
  protocol: null,
  connected: false,
  atr: null
};

const pcsc = pcsclite();

pcsc.on('reader', (reader) => {
  console.log(`[PC/SC] reader detected: ${reader.name}`);
  state.readerName = reader.name;
  state.reader = reader;

  reader.on('error', (err) => {
    console.error(`[PC/SC] reader error (${reader.name}): ${err.message}`);
  });

  reader.on('status', (status) => {
    const changes = reader.state ^ status.state;
    if (!changes) return;

    if ((changes & reader.SCARD_STATE_EMPTY) && (status.state & reader.SCARD_STATE_EMPTY)) {
      console.log(`[PC/SC] card removed from ${reader.name}`);
      if (state.connected) {
        reader.disconnect(reader.SCARD_LEAVE_CARD, () => {});
        state.connected = false;
        state.protocol = null;
      }
    } else if ((changes & reader.SCARD_STATE_PRESENT) && (status.state & reader.SCARD_STATE_PRESENT)) {
      if (status.atr && status.atr.length) {
        state.atr = Buffer.from(status.atr).toString('hex').toUpperCase();
      }
      console.log(`[PC/SC] card present on ${reader.name}, ATR=${state.atr || 'n/a'}`);
    }
  });

  reader.on('end', () => {
    console.log(`[PC/SC] reader removed: ${reader.name}`);
    if (state.readerName === reader.name) {
      state.readerName = null;
      state.reader = null;
      state.protocol = null;
      state.connected = false;
    }
  });
});

pcsc.on('error', (err) => {
  console.error(`[PC/SC] service error: ${err.message}`);
});

function connectCard() {
  return new Promise((resolve, reject) => {
    if (!state.reader) {
      return reject(new Error('연결된 리더기가 없습니다.'));
    }
    const reader = state.reader;
    const share = reader.SCARD_SHARE_SHARED;
    const protos = reader.SCARD_PROTOCOL_T0 | reader.SCARD_PROTOCOL_T1;

    reader.connect({ share_mode: share, protocol: protos }, (err, protocol) => {
      if (err) return reject(err);
      console.log(`[PC/SC] connect ok, protocol=${protocol} (type=${typeof protocol})`);
      state.protocol = typeof protocol === 'number' ? protocol : reader.SCARD_PROTOCOL_T0;
      state.connected = true;
      resolve({ atr: state.atr });
    });
  });
}

function transmitApdu(hex) {
  return new Promise((resolve, reject) => {
    if (!state.reader || !state.connected) {
      return reject(new Error('카드가 연결되어 있지 않습니다. 먼저 RESET을 실행하세요.'));
    }
    const cmd = Buffer.from(hex, 'hex');
    state.reader.transmit(cmd, 512, state.protocol, (err, data) => {
      if (err) return reject(err);
      const respHex = data.toString('hex').toUpperCase();
      const sw = respHex.slice(-4);
      const body = respHex.slice(0, -4);
      resolve({ response: respHex, body, sw });
    });
  });
}

const wss = new WebSocketServer({ port: WS_PORT });
console.log(`[Bridge] WebSocket listening on ws://localhost:${WS_PORT}`);

wss.on('connection', (ws) => {
  console.log('[Bridge] client connected');

  ws.on('message', async (raw) => {
    let msg;
    try {
      msg = JSON.parse(raw.toString());
    } catch {
      return ws.send(JSON.stringify({ type: 'ERROR', message: 'invalid JSON' }));
    }

    try {
      if (msg.action === 'RESET') {
        const result = await connectCard();
        ws.send(JSON.stringify({ type: 'RESET_OK', reader: state.readerName, atr: result.atr }));
      } else if (msg.action === 'TRANSMIT') {
        if (typeof msg.apdu !== 'string') {
          throw new Error('apdu (hex string) 필드가 필요합니다.');
        }
        const result = await transmitApdu(msg.apdu);
        ws.send(JSON.stringify({ type: 'TRANSMIT_OK', ...result }));
      } else {
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
  if (state.reader && state.connected) {
    state.reader.disconnect(state.reader.SCARD_LEAVE_CARD, () => process.exit(0));
  } else {
    process.exit(0);
  }
});
