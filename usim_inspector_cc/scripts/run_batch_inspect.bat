@echo off
chcp 65001 > nul
title USIM 카드 품질검수 - 일괄 처리

setlocal EnableDelayedExpansion
cd /d "%~dp0\.."

where py >nul 2>nul
if errorlevel 1 (
    echo [오류] Python 미설치. https://www.python.org/downloads/
    pause
    exit /b 1
)

py -3.14 -c "import yaml, openpyxl" 2>nul
if errorlevel 1 (
    echo [초기 설정] 패키지 설치...
    py -3.14 -m pip install -r requirements.txt
    if errorlevel 1 (
        echo [오류] 패키지 설치 실패.
        pause
        exit /b 1
    )
)

if "%~1"=="" (
    echo.
    echo === USIM 일괄 검수 도구 ===
    echo.
    set /p TARGET="여러 배치가 들어있는 상위 폴더 경로: "
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
echo  일괄 검수 시작: !TARGET!
echo ============================================
echo.

py -3.14 -m usim_inspector "!TARGET!" --batch
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
