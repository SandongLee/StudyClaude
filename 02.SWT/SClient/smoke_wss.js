const WebSocket = require('ws');

const tests = [
  { label: 'wss + allowed origin', url: 'wss://localhost:8444', origin: 'https://localhost:8443', send: { action: 'CONNECT' } },
  { label: 'wss + bad origin', url: 'wss://localhost:8444', origin: 'https://evil.example', send: null },
  { label: 'wss + no origin (SECURE rejects)', url: 'wss://localhost:8444', origin: null, send: null }
];

(async () => {
  for (const t of tests) {
    await new Promise((done) => {
      const opts = { rejectUnauthorized: false };
      if (t.origin) opts.origin = t.origin;
      const ws = new WebSocket(t.url, opts);
      const timer = setTimeout(() => { ws.terminate(); console.log(`[${t.label}] TIMEOUT`); done(); }, 3000);
      let opened = false;
      ws.on('open', () => {
        opened = true;
        console.log(`[${t.label}] OPEN`);
        if (t.send) ws.send(JSON.stringify(t.send));
        else { ws.close(); clearTimeout(timer); done(); }
      });
      ws.on('message', (raw) => {
        console.log(`[${t.label}] RECV ${raw.toString().slice(0, 140)}`);
        if (opened && t.send) { ws.close(); clearTimeout(timer); done(); }
      });
      ws.on('unexpected-response', (req, res) => {
        console.log(`[${t.label}] REJECTED HTTP ${res.statusCode}`);
        clearTimeout(timer); done();
      });
      ws.on('error', (e) => {
        if (!opened) { console.log(`[${t.label}] ERROR ${e.message}`); clearTimeout(timer); done(); }
      });
    });
  }
  process.exit(0);
})();
