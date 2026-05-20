@echo off
chcp 65001 > nul
title USIM 카드 품질검수 - 단일 배치

setlocal EnableDelayedExpansion

REM 프로젝트 루트로 이동 (이 .bat은 scripts/ 폴더 안에 있음)
cd /d "%~dp0\.."

where py >nul 2>nul
if errorlevel 1 (
    echo.
    echo [오류] Python이 설치되어 있지 않거나 PATH에 등록되지 않았습니다.
    echo https://www.python.org/downloads/ 에서 Python 3.10 이상을 설치하세요.
    echo 설치 시 "Add Python to PATH" 체크박스를 반드시 켜세요.
    echo.
    pause
    exit /b 1
)

REM 패키지 설치 확인 (최초 1회 자동)
py -3.14 -c "import yaml, openpyxl" 2>nul
if errorlevel 1 (
    echo [초기 설정] 필요한 Python 패키지를 설치합니다... ^(최초 1회만^)
    py -3.14 -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [오류] 패키지 설치 실패. 인터넷 연결을 확인하세요.
        pause
        exit /b 1
    )
)

REM 입력 경로
if "%~1"=="" (
    echo.
    echo === USIM 카드 품질검수 도구 ===
    echo.
    set /p TARGET="검수할 배치 폴더 경로를 입력하세요: "
) else (
    set "TARGET=%~1"
)

if not exist "!TARGET!" (
    echo [오류] 폴더가 존재하지 않습니다: !TARGET!
    pause
    exit /b 1
)

echo.
echo ============================================
echo  검수 시작: !TARGET!
echo ============================================
echo.

py -3.14 -m usim_inspector "!TARGET!"
set EXITCODE=!errorlevel!

echo.
echo ============================================
if !EXITCODE! equ 0 (
    echo  검수 종료 ^(정상^)
) else (
    echo  검수 종료 ^(오류 코드 !EXITCODE!^)
)
echo ============================================
echo.

if exist "reports" (
    set /p OPENREPORT="보고서 폴더를 여시겠습니까? (Y/N): "
    if /i "!OPENREPORT!"=="Y" start "" "reports"
)

pause
endlocal
