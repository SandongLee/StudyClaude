# SClient — 로컬 PC/SC ↔ WebSocket 브리지

브라우저(SWebserver 화면)와 OS의 PC/SC 스택 사이를 중계하는 Node.js 에이전트입니다.

## 사전 준비

- Node.js 18 이상
- 스마트카드 리더기 CCID 드라이버 설치
- Windows: "Smart Card" 서비스가 시작 상태인지 확인 (`services.msc`)

> `@pokusew/pcsclite`는 네이티브 모듈이므로 빌드 툴체인이 필요할 수 있습니다.
> - Windows: `npm install --global windows-build-tools` (또는 Visual Studio Build Tools)
> - macOS: Xcode Command Line Tools
> - Linux: `libpcsclite-dev`, `pcscd` 데몬

## 설치 & 실행

```bash
npm install
node bridge.js
```

기본적으로 `ws://localhost:8081`에서 대기합니다.

## 프로토콜

요청(브라우저 → 브리지):

| action     | 추가 필드      | 설명                          |
|------------|----------------|-------------------------------|
| `RESET`    | -              | 카드 연결 후 ATR 반환         |
| `TRANSMIT` | `apdu` (hex)   | APDU 송신 후 응답 반환        |

응답(브리지 → 브라우저):

| type          | 필드                              |
|---------------|-----------------------------------|
| `RESET_OK`    | `reader`, `atr`                   |
| `TRANSMIT_OK` | `response`, `body`, `sw`          |
| `ERROR`       | `message`                         |
