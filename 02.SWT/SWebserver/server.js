const path = require('path');
const express = require('express');

const app = express();
const PORT = process.env.PORT || 8080;

app.use(express.json());
app.use(express.static(path.join(__dirname, 'public')));

app.get('/api/health', (_req, res) => {
  res.json({ status: 'ok', service: 'SWebserver', time: new Date().toISOString() });
});

app.get('/api/config', (_req, res) => {
  res.json({
    bridgeUrl: 'ws://localhost:8081',
    version: '0.1.0'
  });
});

app.listen(PORT, () => {
  console.log(`[SWebserver] listening on http://localhost:${PORT}`);
});
