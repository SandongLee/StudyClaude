# SWT 프로토타입 - 설치 / 실행 / E2E 검증 기록

> 본 문서는 `CLAUDE.md` 명세에 따른 최소 기능 프로토타입의 **설치 절차**, **로컬 브라우저 접속 방법**, **실측 E2E 검증 결과**를 기록합니다.

---

## 1. 검증 환경

| 항목 | 값 |
|---|---|
| OS | Windows 11 Pro |
| Node.js | v24.16.0 (winget `OpenJS.NodeJS.LTS` 자동 설치) |
| npm | 11.13.0 |
| Smart Card 서비스 (`SCardSvr`) | Running (StartType: Manual) |
| 사용 리더기 | **Gemplus USB Smart Card Reader 0** |
| 카드 ATR | `3BDF9500803F87A08031E073FE211B67E2017E830F9000D2` |
| Docker / Compose | 29.5.2 / v5.1.4 |

---

## 2. 진행된 작업 요약

1. PDF 명세서를 `CLAUDE.md`로 정리
2. 디렉토리 구조 생성: `SWebserver/`, `SClient/`, `doc/`
3. SWebserver 구현
   - `Dockerfile`, `docker-compose.yml`, `package.json`, `server.js`
   - `public/index.html` (Card Reset / APDU 입력 / Send APDU / 응답창 UI)
4. SClient 구현
   - `package.json`, `bridge.js` (WebSocket 8081 ↔ PC/SC 중계)
5. 의존성 설치
   - `@pokusew/pcsclite` 버전을 명세서의 `^1.0.3` → 실제 존재 버전 `^0.6.0`으로 수정
   - 네이티브 모듈(`build/`) 빌드 성공 (별도 VS Build Tools 불필요)
6. 브라우저 ↔ 브리지 ↔ 카드 E2E 검증 (발견된 버그 2건 수정 — 아래 4번 항목)
7. **Reader 관리 UI 추가** — 다중 리더 listbox + 「연결 / Cold Reset / Warm Reset / 연결 끊기」 4버튼
   - 브리지: `readers = Map<name, info>` 다중 리더 관리, `READERS` 푸시, `CONNECT/DISCONNECT/WARM_RESET/COLD_RESET` 액션 추가
   - **세 가지 동작을 PC/SC 호출 시퀀스로 명확히 분리**
     - 연결 = `reader.connect()` 한 번 (단순 attach)
     - Warm Reset = `disconnect(SCARD_RESET_CARD)` + `connect` — 카드 전원 유지, 논리적 리셋
     - Cold Reset = `disconnect(SCARD_UNPOWER_CARD)` + `connect` — 카드 전원 사이클(off → on)
   - `@pokusew/pcsclite` 0.6.0에 `reconnect` 미지원이라 두 단계 호출로 구현
   - UI: 두 카드(Reader 선택 / Card Reset)를 한 카드(「1. Reader 선택 / 카드 제어」)로 통합, 버튼 순서 「연결 → Cold Reset → Warm Reset → 연결 끊기」 + 색상 분리(blue/cyan/orange/red)
8. **Auto Get Response (61xx/6Cxx 자동 chained APDU)** — 응답 로그 헤더에 체크박스
   - 체크 시: `61xx` → `<CLA>C00000<xx>` GET RESPONSE, `6Cxx` → 마지막 APDU의 Le만 교체 재전송. 안전장치 `AUTO_CHAIN_MAX=8`.
9. **SECURE 모드 (HTTPS + wss + Origin 화이트리스트)** — §8 참조
   - `selfsigned` 기반 `gen-cert.js`로 self-signed 인증서 자동 발급
   - 브리지·서버 모두 `SECURE=1` 환경변수로 토글, `/api/config` 가 자동으로 `wss` URL 반환
   - `verifyClient`로 Origin 검증 — SECURE 모드에서는 Origin 헤더 없는 연결도 거부

---

## 3. 디렉토리 구조 (최종)

```
SWT/
├── CLAUDE.md                # 개발 명세서
├── .gitignore
├── .claude/
│   └── launch.json          # Preview MCP용 서버 설정
├── certs/                   # (gitignore) gen-cert.js로 자동 생성
│   ├── server.key
│   └── server.crt
├── SWebserver/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── .dockerignore
│   ├── package.json
│   ├── server.js            # SECURE=1 시 HTTPS, /api/config 동적 bridgeUrl
│   ├── public/index.html    # 1) Reader 선택/카드 제어, 2) APDU 전송, 3) 응답 로그(Auto Get Response)
│   └── node_modules/
├── SClient/
│   ├── package.json         # ws, @pokusew/pcsclite, selfsigned
│   ├── bridge.js            # SECURE=1 시 wss, 항상 Origin 화이트리스트
│   ├── gen-cert.js          # self-signed 인증서 발급
│   ├── smoke_e2e.js         # 평문 WS RESET/TRANSMIT 자가 검증
│   ├── smoke_origin.js      # Origin 화이트리스트 검증
│   ├── smoke_wss.js         # wss 핸드셰이크 + Origin 검증
│   ├── README.md
│   └── node_modules/
└── doc/
    ├── SWT_spec_original.pdf
    └── SETUP_AND_E2E.md     # 본 문서
```

---

## 4. E2E 진행 중 발견 & 수정한 버그

### 4-1. ATR이 `null`로 반환되던 문제
- **증상**: RESET 응답 JSON에서 `"atr": null`
- **원인**: `reader.connect` 콜백 시점에 `reader.state.atr`이 아직 비어있음
- **수정**: `reader.on('status', ...)`에서 `status.atr`을 `state.atr`로 캐싱하고 RESET 응답에서 그 값을 사용
- **파일**: [SClient/bridge.js](../SClient/bridge.js)

### 4-2. TRANSMIT 시 "Third argument must be an integer"
- **증상**: 첫 RESET 직후 `transmit()` 호출이 "Third argument must be an integer"로 거부
- **원인**: `reader.connect` 콜백의 `protocol` 인자가 간헐적으로 정수 외 타입으로 들어오는 케이스
- **수정**: `typeof protocol === 'number'` 검증 + 실패 시 `SCARD_PROTOCOL_T0` fallback

### 검증 결과 (실측)

#### 4-A. 초기 평문 모드 (Card Reset 단독)
| 송신 APDU | 수신 응답 | 상태 워드 | 의미 |
|---|---|---|---|
| (RESET) | ATR `3BDF9500…9000D2` | – | 카드 정상 리셋 |
| `00A4040000` (SELECT, empty AID) | `6189` | `6189` | 정상 처리, 응답 137B 사용 가능 |
| `0084000008` (GET CHALLENGE 8B) | `6D00` | `6D00` | 이 카드 미지원 INS |
| `00A40400023F00` (SELECT MF) | `6A82` | `6A82` | File not found |

#### 4-B. Reader 관리 UI 동작 (통합된 「1. Reader 선택 / 카드 제어」 박스)
| 액션 | 브리지 PC/SC 호출 | UI 로그 |
|---|---|---|
| `CONNECT` | `reader.connect()` | `연결됨: Gemplus USB Smart Card Reader 0 (ATR=3BDF95…0076)` |
| `COLD_RESET` | `disconnect(SCARD_UNPOWER_CARD)` + `connect` | `Cold Reset OK: ... (ATR=3BDF95…0076)` (브리지 로그: `cold reset: power cycled`) |
| `WARM_RESET` | `disconnect(SCARD_RESET_CARD)` + `connect` | `Warm Reset OK: ... (ATR=3BDF95…0076)` |
| `TRANSMIT 00A4040000` | `reader.transmit(...)` | `<= 6112 (SW=6112)` |
| `DISCONNECT` | `disconnect(SCARD_LEAVE_CARD)` | `연결 끊김: Gemplus USB Smart Card Reader 0` |

> 같은 카드라 ATR 값은 동일하게 회신되지만, 브리지의 PC/SC 호출 시퀀스가 명확히 분리되어 있어 디버깅 시 의도를 추적할 수 있습니다.

#### 4-C. Auto Get Response (체크박스 ON)
입력: `00A4040000`
```
=> TRANSMIT 00A4040000
<= 6112  (SW=6112)
[auto] => TRANSMIT 00C0000012
<= 6F108408A000000003000000A5049F6501FF9000  (SW=9000)
```
- 응답 분석: `6F10` (FCI Template) → `8408 A000000003000000` (AID=Visa) → `A504 9F6501FF` → SW `9000`
- 자동 체인 1회, SW=9000으로 자연 종료

#### 4-D. Origin 화이트리스트
| 모드 | 시나리오 | 결과 |
|---|---|---|
| 평문 ws | Origin = `http://localhost:8080` | OPEN ✅ |
| 평문 ws | Origin = `http://evil.example` | **HTTP 403** ✅ |
| 평문 ws | Origin 없음 (Node 디폴트) | OPEN (개발 모드 허용) |
| wss | Origin = `https://localhost:8443` | OPEN + READERS 푸시 수신 ✅ |
| wss | Origin = `https://evil.example` | **HTTP 403** ✅ |
| wss | Origin 없음 | **HTTP 403** (SECURE는 헤더 없는 연결도 거부) ✅ |
| HTTPS | `GET /api/config` | `{"bridgeUrl":"wss://localhost:8444","secure":true,"version":"0.2.0"}` ✅ |

---

## 5. 로컬 PC에서 브라우저로 접속하는 방법

> 두 가지 컴포넌트가 동시에 떠 있어야 합니다.
> - **SWebserver** (포트 8080) – UI 호스팅
> - **SClient bridge.js** (포트 8081) – 카드 리더 중계

### 5-1. 최초 1회 사전 준비

```powershell
# 0) 리더기를 USB에 연결합니다.

# 1) Smart Card 서비스가 Running인지 확인 (필요 시 시작)
Get-Service SCardSvr
# 멈춰있다면:
Start-Service SCardSvr

# 2) Node.js 설치 (이미 설치되어 있다면 생략)
winget install --id OpenJS.NodeJS.LTS --silent

# 3) 의존성 설치 (각 폴더 1회씩)
cd C:\Users\netbomb\Desktop\SKTL\OneDrive\일\70.Claude\02.SWT\SClient
npm install

cd ..\SWebserver
npm install
```

### 5-2. 매번 사용할 때 (권장: 2개 터미널)

**터미널 ① — 브리지 (호스트 OS에서 직접 실행)**

```powershell
cd C:\Users\netbomb\Desktop\SKTL\OneDrive\일\70.Claude\02.SWT\SClient
node bridge.js
```

정상 기동 시 다음 메시지가 출력됩니다:

```
[Bridge] WebSocket listening on ws://localhost:8081
[PC/SC] reader detected: Gemplus USB Smart Card Reader 0
[PC/SC] card present on Gemplus USB Smart Card Reader 0, ATR=3BDF95…
```

**터미널 ② — 웹 서버 (두 옵션 중 택1)**

옵션 A. Docker (명세서 기본 방식)
```powershell
cd C:\Users\netbomb\Desktop\SKTL\OneDrive\일\70.Claude\02.SWT\SWebserver
docker compose up --build -d
```

옵션 B. Node 직접 실행 (Docker 없이)
```powershell
cd C:\Users\netbomb\Desktop\SKTL\OneDrive\일\70.Claude\02.SWT\SWebserver
node server.js
```

### 5-3. 브라우저 접속

브라우저 주소창에 입력:

```
http://localhost:8080
```

화면 우측 상단의 **`Bridge: connected`** 표시(녹색)가 보이면 브리지 연결 OK.

### 5-4. 사용 흐름

#### 화면 구성 (3개 카드)
1. **1. Reader 선택 / 카드 제어** — 리스트박스 + 4개 버튼(연결 / Cold Reset / Warm Reset / 연결 끊기)
2. **2. APDU 전송** — Hex 입력창 + Send APDU
3. **3. 응답 로그** — Auto Get Response 토글 + textarea + Clear

#### 버튼 의미와 색
| 버튼 | 색 | 의미 |
|---|---|---|
| 연결 | 청색 | `reader.connect()` — 단순 세션 attach |
| Cold Reset | cyan | 카드 전원 사이클(off → on), ATR 새로 확인 |
| Warm Reset | 주황 | 전원 유지 + 논리적 리셋 |
| 연결 끊기 | 빨강 | 세션 해제 |

#### 사용 흐름 예시
1. 리스트박스에서 리더기 선택
   - `💳` = 카드 있음, `∅` = 없음, `✓연결됨` = 현재 세션
2. **「연결」** → `연결됨: <reader> (ATR=...)`
3. APDU 입력창에 Hex 입력 (기본값 `00A4040000`) → **「Send APDU」**
4. 필요 시 **「Cold Reset」** 또는 **「Warm Reset」** 으로 카드 상태 갱신
5. **응답 로그 우상단 「Auto Get Response」** 체크 시 `61xx`/`6Cxx`에 대해 자동 후속 APDU
6. 종료 시 **「연결 끊기」**

#### 기타
- **「Clear」** 로 로그 초기화
- 리더기/카드 hot-plug는 자동 감지되어 listbox에 반영됨

---

## 6. 종료 방법

```powershell
# 브리지: 해당 터미널에서 Ctrl+C

# Docker 서버:
cd C:\Users\netbomb\Desktop\SKTL\OneDrive\일\70.Claude\02.SWT\SWebserver
docker compose down

# Node 직접 실행 서버: 해당 터미널에서 Ctrl+C
```

---

## 7. 트러블슈팅

| 증상 | 원인 / 해결 |
|---|---|
| 화면에 `Bridge: disconnected`(빨강) | `bridge.js`가 안 떠 있거나 8081 포트 점유. 터미널 ① 재기동. |
| 브리지 콘솔에 reader가 안 보임 | USB 인식 실패. 장치 관리자에서 리더기 확인 + `SCardSvr` 시작 상태 확인. |
| `npm install` 시 `@pokusew/pcsclite` 오류 | 패키지 버전이 `^0.6.0`인지 확인 ([SClient/package.json](../SClient/package.json)). |
| RESET 응답 `atr: null` | 카드 미삽입. 카드 삽입 후 다시 RESET. |
| TRANSMIT `ERROR: ...` | 카드가 분리됐거나 RESET 누락. RESET을 먼저 실행. |
| Docker 8080 충돌 | 다른 컨테이너가 8080 사용 중. `docker ps`로 확인 후 정리. |

---

## 8. SECURE 모드 (HTTPS + wss + Origin 화이트리스트)

평문 모드(8080/8081) 외에 자체 서명 인증서 기반의 보안 모드를 지원합니다.

### 8-1. 인증서 발급 (최초 1회)

```powershell
cd C:\Users\netbomb\Desktop\SKTL\OneDrive\일\70.Claude\02.SWT\SClient
npm install
node gen-cert.js
```

→ `../certs/server.key`, `../certs/server.crt` 생성됨. `--force` 옵션으로 재발급 가능.

### 8-2. SECURE 모드 실행

**터미널 ① — 브리지(wss)**
```powershell
cd C:\Users\netbomb\Desktop\SKTL\OneDrive\일\70.Claude\02.SWT\SClient
$env:SECURE = '1'
node bridge.js
```

기동 로그 예:
```
[Bridge] WSS listening on wss://localhost:8444
[Bridge] allowed origins: https://localhost:8443
```

**터미널 ② — 서버(HTTPS)**
```powershell
cd C:\Users\netbomb\Desktop\SKTL\OneDrive\일\70.Claude\02.SWT\SWebserver
$env:SECURE = '1'
node server.js
```

→ `https://localhost:8443` 으로 접속. 자체 서명 인증서이므로 브라우저에서 **「고급 → 안전하지 않음으로 이동」** 한 번만 수락하면 됩니다. 페이지의 `/api/config` 가 자동으로 `wss://localhost:8444` 를 가리키므로 추가 설정은 불필요합니다.

### 8-3. 환경변수

| 변수 | 기본값(평문) | 기본값(SECURE) | 설명 |
|---|---|---|---|
| `SECURE` | – | `1` | HTTPS/wss 모드 활성화 |
| `SWEB_PORT` | `8080` | `8443` | 웹 서버 포트 |
| `BRIDGE_PORT` | `8081` | `8444` | 브리지 포트 |
| `BRIDGE_HOST` | `localhost` | `localhost` | 브리지 호스트(SWebserver가 알려주는 값) |
| `ALLOWED_ORIGINS` | `http://localhost:8080` | `https://localhost:8443` | 콤마 구분 화이트리스트 |

### 8-4. Origin 화이트리스트 검증 결과

`smoke_origin.js` (평문 8081) / `smoke_wss.js` (wss 8444) 실측:

| 시나리오 | 결과 |
|---|---|
| 평문 / Origin = `http://localhost:8080` | **OPEN** ✅ |
| 평문 / Origin = `http://evil.example` | **HTTP 403** ✅ |
| 평문 / Origin 없음 | OPEN(개발 모드) |
| wss / Origin = `https://localhost:8443` | **OPEN** + READERS 푸시 수신 ✅ |
| wss / Origin = `https://evil.example` | **HTTP 403** ✅ |
| wss / Origin 없음 | **HTTP 403** (SECURE는 헤더 없는 연결도 거부) ✅ |

### 8-5. 운영 환경 마이그레이션 시 체크리스트
- 자체 서명 인증서를 정식 인증서(예: Let's Encrypt 또는 사내 CA 발급) 로 교체.
- `ALLOWED_ORIGINS`를 실제 운영 호스트로 명시(콤마 구분).
- Docker로 띄울 경우 `certs/`를 read-only 볼륨으로 마운트하고 `SECURE=1`, `SWEB_PORT=8443` 환경변수 전달.
- 브라우저 mixed content 차단을 피하려면 페이지(HTTPS)와 브리지(wss)가 반드시 같은 보안 등급이어야 함.

---

## 9. 다음 단계 후보

- **(c)** APDU 명령 프리셋 버튼 (SELECT MF, READ BINARY, GET DATA, …) UI 확장
- **(e)** 명령/응답 히스토리 영구 저장(JSONL) 및 다운로드 기능
- ~~**(f)** Chained APDU(`61xx`, `6Cxx`) 자동 GET RESPONSE 처리~~ ✅ 완료
- ~~**(b)** wss/HTTPS 운영 모드 + Origin 화이트리스트~~ ✅ 완료
