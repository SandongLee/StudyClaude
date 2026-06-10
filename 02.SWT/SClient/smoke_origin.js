const WebSocket = require('ws');

const cases = [
  { label: 'origin allowed', origin: 'http://localhost:8080' },
  { label: 'origin rejected', origin: 'http://evil.example' },
  { label: 'no origin (node default)', origin: null }
];

(async () => {
  for (const c of cases) {
    await new Promise((done) => {
      const opts = c.origin ? { origin: c.origin } : {};
      const ws = new WebSocket('ws://localhost:8081', opts);
      const timer = setTimeout(() => { ws.terminate(); done(); }, 1500);
      ws.on('open', () => {
        console.log(`[${c.label}] OPEN`);
        clearTimeout(timer);
        ws.close();
        done();
      });
      ws.on('unexpected-response', (req, res) => {
        console.log(`[${c.label}] REJECTED (HTTP ${res.statusCode})`);
        clearTimeout(timer);
        done();
      });
      ws.on('error', (e) => {
        console.log(`[${c.label}] ERROR ${e.message}`);
        clearTimeout(timer);
        done();
      });
    });
  }
  process.exit(0);
})();
