@echo off
REM ============================================================
REM  Abre o Prospector.
REM
REM  O Prospector agora e um aplicativo de desktop. Este atalho
REM  existe so para quem prefere rodar da pasta do projeto; o
REM  jeito normal e o icone no Menu Iniciar.
REM ============================================================
setlocal
cd /d "%~dp0"

if exist "%LOCALAPPDATA%\Programs\Prospector\Prospector.exe" (
    start "" "%LOCALAPPDATA%\Programs\Prospector\Prospector.exe"
    exit /b 0
)

if exist "backend\dist\Prospector\Prospector.exe" (
    start "" "backend\dist\Prospector\Prospector.exe"
    exit /b 0
)

echo.
echo  O Prospector ainda nao foi compilado.
echo.
echo    1. Rode compilar.bat  (compila tudo)
echo    2. Abra backend\dist\ProspectorSetup.exe  (instala)
echo.
pause
