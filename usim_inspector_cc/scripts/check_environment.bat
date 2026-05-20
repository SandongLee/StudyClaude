@echo off
chcp 65001 > nul
title USIM 검수 - 환경 점검

setlocal
cd /d "%~dp0\.."

echo ============================================
echo  USIM 검수 도구 - 환경 점검
echo ============================================
echo.

where py >nul 2>nul
if errorlevel 1 (
    echo [1] Python: ❌ 미설치
    echo     → https://www.python.org/downloads/
    pause
    exit /b 1
)

echo [1] Python:
py -3.14 --version
echo.

echo [2] Python 패키지:
py -3.14 -c "import yaml; print('     ✅ pyyaml:', yaml.__version__)" 2>nul
if errorlevel 1 echo     ❌ pyyaml 미설치 ^(run_inspect.bat 실행 시 자동 설치^)
py -3.14 -c "import openpyxl; print('     ✅ openpyxl:', openpyxl.__version__)" 2>nul
if errorlevel 1 echo     ❌ openpyxl 미설치
echo.

echo [3] inspector 자체 진단:
py -3.14 -m usim_inspector --check-env
echo.

pause
endlocal
