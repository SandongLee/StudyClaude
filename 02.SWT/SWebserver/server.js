const fs = require('fs');
const path = require('path');
const https = require('https');
const express = require('express');

const SECURE = process.env.SECURE === '1' || process.env.SECURE === 'true';
const PORT = parseInt(process.env.SWEB_PORT || process.env.PORT || (SECURE ? '8443' : '8080'), 10);
const BRIDGE_PORT = parseInt(process.env.BRIDGE_PORT || (SECURE ? '8444' : '8081'), 10);
const BRIDGE_HOST = process.env.BRIDGE_HOST || 'localhost';

const app = express();

app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

app.get('/api/health', (_req, res) => {
  res.json({ status: 'ok', service: 'SWebserver', secure: SECURE, time: new Date().toISOString() });
});

app.get('/api/config', (_req, res) => {
  const wsProto = SECURE ? 'wss' : 'ws';
  res.json({
    bridgeUrl: `${wsProto}://${BRIDGE_HOST}:${BRIDGE_PORT}`,
    secure: SECURE,
    version: '0.2.0'
  });
});

if (SECURE) {
  const certDir = path.resolve(__dirname, '..', 'certs');
  const keyPath = path.join(certDir, 'server.key');
  const crtPath = path.join(certDir, 'server.crt');
  if (!fs.existsSync(keyPath) || !fs.existsSync(crtPath)) {
    console.error(`[SWebserver] 인증서 없음: ${certDir}\n먼저 "cd ../SClient && node gen-cert.js"를 실행하세요.`);
    process.exit(1);
  }
  const opts = { key: fs.readFileSync(keyPath), cert: fs.readFileSync(crtPath) };
  https.createServer(opts, app).listen(PORT, () => {
    console.log(`[SWebserver] HTTPS listening on https://localhost:${PORT}`);
  });
} else {
  app.listen(PORT, () => {
    console.log(`[SWebserver] HTTP listening on http://localhost:${PORT}`);
  });
}
