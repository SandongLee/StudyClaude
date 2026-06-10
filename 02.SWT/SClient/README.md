# SClient — 로컬 PC/SC ↔ WebSocket 브리지

브라우저(SWebserver 화면)와 OS의 PC/SC 스택 사이를 중계하는 Node.js 에이전트입니다.

## 사전 준비

- Node.js 18 이상
- 스마트카드 리더기 CCID 드라이버 설치
- Windows: "Smart Card" 서비스가 시작 상태인지 확인 (`services.msc`)

> `@pokusew/pcsclite`는 네이티브 모듈이므로 빌드 툴체인이 필요할 수 있습니다.
> - Windows: Visual Studio Build Tools (없어도 Windows 10+에서 prebuilt가 동작하는 경우 多)
> - macOS: Xcode Command Line Tools
> - Linux: `libpcsclite-dev`, `pcscd` 데몬

## 설치 & 실행

### 평문 모드 (기본)

```bash
npm install
node bridge.js
```

기본 대기 주소: `ws://localhost:8081`, 허용 Origin: `http://localhost:8080`.

### SECURE 모드 (HTTPS + wss + Origin 화이트리스트)

```bash
npm install
node gen-cert.js           # 최초 1회 — ../certs/server.{key,crt} 발급
$env:SECURE = '1'          # PowerShell
node bridge.js
```

기본 대기 주소: `wss://localhost:8444`, 허용 Origin: `https://localhost:8443`.

### 환경변수

| 변수 | 기본(평문) | 기본(SECURE) | 설명 |
|---|---|---|---|
| `SECURE` | – | `1` | TLS(wss) 활성화 |
| `BRIDGE_PORT` | `8081` | `8444` | 브리지 포트 |
| `SWEB_PORT` | `8080` | `8443` | (Origin 기본값 계산용) |
| `ALLOWED_ORIGINS` | `http://localhost:8080` | `https://localhost:8443` | 콤마 구분 화이트리스트 |

> `ALLOWED_ORIGINS` 화이트리스트에 매칭되지 않는 연결은 HTTP 403으로 거부됩니다.
> SECURE 모드에서는 Origin 헤더가 없는 연결도 거부합니다(개발용 Node 클라이언트 포함).

## 프로토콜

### 요청 (브라우저 → 브리지)

| action | 추가 필드 | 설명 |
|---|---|---|
| `LIST_READERS` | – | 현재 리더 목록 반환 |
| `CONNECT` | `reader`(name) | 해당 리더에 단순 attach (`reader.connect`) |
| `DISCONNECT` | – | 현재 세션 해제 (`SCARD_LEAVE_CARD`) |
| `WARM_RESET` | – | 현재 세션 카드의 논리적 리셋 (`disconnect(SCARD_RESET_CARD)` + `connect`) |
| `COLD_RESET` / `RESET` | `reader`(opt) | 카드 전원 사이클 (`disconnect(SCARD_UNPOWER_CARD)` + `connect`) |
| `TRANSMIT` | `apdu`(hex) | APDU 송신 후 응답 회신 |

`CONNECT` / `COLD_RESET` / `RESET`는 `reader`를 생략하면 현재 세션 → 첫 리더 순으로 자동 선택됩니다.

### 응답 (브리지 → 브라우저)

| type | 필드 | 비고 |
|---|---|---|
| `READERS` | `readers: [{name, hasCard, atr, connected}]` | 연결 직후 + 리더/카드 상태 변경 시 브로드캐스트 |
| `CONNECT_OK` | `reader`, `atr`, `protocol` | `reader.connect` 성공 |
| `DISCONNECT_OK` | `reader` | – |
| `WARM_RESET_OK` | `reader`, `atr`, `protocol` | – |
| `COLD_RESET_OK` | `reader`, `atr`, `protocol` | 카드 전원 사이클 완료 후 |
| `TRANSMIT_OK` | `response`(hex), `body`(hex), `sw`(hex) | – |
| `ERROR` | `message` | – |

## 헬퍼 스크립트

| 파일 | 용도 |
|---|---|
| `gen-cert.js` | self-signed 인증서 발급 (`../certs/server.{key,crt}`). `--force`로 재발급. |
| `smoke_e2e.js` | 평문 `ws`로 RESET/TRANSMIT 시퀀스 자가 검증 |
| `smoke_origin.js` | 평문 `ws`에 대해 Origin 화이트리스트 동작 검증 (allowed/rejected/no-origin) |
| `smoke_wss.js` | `wss`에 대해 핸드셰이크 + Origin 검증 (자체 서명 인증서 신뢰 안 함 → `rejectUnauthorized:false`) |
