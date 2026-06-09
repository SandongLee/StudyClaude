const WebSocket = require('ws');

const ws = new WebSocket('ws://localhost:8081');
const log = (...a) => console.log(new Date().toISOString().slice(11, 23), ...a);

const queue = [
  { action: 'RESET' },
  { action: 'TRANSMIT', apdu: '0084000008' },
  { action: 'TRANSMIT', apdu: '00A40400023F00' }
];
let idx = 0;

ws.on('open', () => {
  log('OPEN');
  next();
});

function next() {
  if (idx >= queue.length) {
    log('DONE');
    ws.close();
    return;
  }
  const m = queue[idx++];
  log('>> SEND', JSON.stringify(m));
  ws.send(JSON.stringify(m));
}

ws.on('message', (raw) => {
  log('<< RECV', raw.toString());
  setTimeout(next, 200);
});
ws.on('close', () => { log('CLOSED'); process.exit(0); });
ws.on('error', (e) => { log('ERR', e.message); process.exit(1); });

setTimeout(() => { log('TIMEOUT'); process.exit(2); }, 8000);
