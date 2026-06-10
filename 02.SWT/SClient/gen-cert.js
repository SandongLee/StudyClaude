const fs = require('fs');
const path = require('path');
const selfsigned = require('selfsigned');

const certDir = path.resolve(__dirname, '..', 'certs');
const keyPath = path.join(certDir, 'server.key');
const crtPath = path.join(certDir, 'server.crt');

if (fs.existsSync(keyPath) && fs.existsSync(crtPath) && !process.argv.includes('--force')) {
  console.log(`인증서가 이미 존재합니다:\n  ${keyPath}\n  ${crtPath}`);
  console.log('재생성하려면 --force 옵션을 사용하세요.');
  process.exit(0);
}

fs.mkdirSync(certDir, { recursive: true });

const attrs = [
  { name: 'commonName', value: 'localhost' },
  { name: 'organizationName', value: 'SWT Local Dev' }
];
const opts = {
  days: 365,
  algorithm: 'sha256',
  keySize: 2048,
  extensions: [
    {
      name: 'subjectAltName',
      altNames: [
        { type: 2, value: 'localhost' },
        { type: 7, ip: '127.0.0.1' },
        { type: 7, ip: '::1' }
      ]
    }
  ]
};

const pems = selfsigned.generate(attrs, opts);
fs.writeFileSync(keyPath, pems.private);
fs.writeFileSync(crtPath, pems.cert);

console.log('self-signed 인증서를 생성했습니다:');
console.log(`  KEY : ${keyPath}`);
console.log(`  CERT: ${crtPath}`);
console.log(`  fingerprint: ${pems.fingerprint}`);
console.log('\n브라우저에서 처음 접속 시 "안전하지 않음" 경고를 한 번 수락해야 합니다.');
