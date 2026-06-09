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
6. 브라우저 ↔ 브리지 ↔ 카드 E2E 검증
   - 발견된 버그 2건 수정 (아래 4번 항목)

---

## 3. 디렉토리 구조 (최종)

```
SWT/
├── CLAUDE.md                # 개발 명세서
├── .gitignore
├── .claude/
│   └── launch.json          # Preview MCP용 서버 설정
├── SWebserver/
│   ├── Dockerfile
│   ├── docker-compose.yml
│   ├── .dockerignore
│   ├── package.json
│   ├── server.js
│   ├── public/index.html
│   └── node_modules/        # 로컬 실행용
├── SClient/
│   ├── package.json
│   ├── bridge.js
│   ├── smoke_e2e.js         # WebSocket 자가 검증 스크립트
│   ├── README.md
│   └── node_modules/
└── doc/
    ├── SWT_spec_original.pdf
    ├── SETUP_AND_E2E.md     # 본 문서
    ├── bridge.log
    └── bridge.err.log
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

| 송신 APDU | 수신 응답 | 상태 워드 | 의미 |
|---|---|---|---|
| (RESET) | ATR `3BDF9500…9000D2` | – | 카드 정상 리셋 |
| `00A4040000` (SELECT, empty AID) | `6189` | `6189` | 정상 처리, 응답 데이터 137바이트 사용 가능 |
| `0084000008` (GET CHALLENGE 8B) | `6D00` | `6D00` | 이 카드 미지원 INS (정상 카드 응답) |
| `00A40400023F00` (SELECT MF) | `6A82` | `6A82` | File not found (카드별 응답) |

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

1. **`Card Reset`** 버튼 클릭 → 응답창에 `ATR: ...` 출력
2. APDU 입력창에 헥사 문자열 입력 (기본값 `00A4040000`)
3. **`Send APDU`** 버튼 클릭 → 응답창에 `<= 응답Hex (SW=상태워드)` 출력
4. **`Clear`** 버튼으로 로그 초기화

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

## 8. 다음 단계 후보

- **(b)** wss/HTTPS 운영 모드 + Origin 화이트리스트
- **(c)** APDU 명령 프리셋 버튼 (SELECT MF, READ BINARY, GET DATA, …) UI 확장
- **(e)** 명령/응답 히스토리 영구 저장(JSONL) 및 다운로드 기능
- **(f)** Chained APDU(`61xx`, `6Cxx`) 자동 GET RESPONSE 처리
