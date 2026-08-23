@echo off
REM ============================================================
REM  Compila o Prospector como aplicativo de desktop.
REM  Resultado: backend\dist\ProspectorSetup.exe  (arquivo unico
REM  para entregar a alguem) e backend\dist\Prospector\ (a pasta
REM  do programa, de onde o instalador e montado).
REM ============================================================
setlocal
cd /d "%~dp0"

echo.
echo  Compilando o Prospector
echo  -----------------------
echo.

if not exist "backend\.venv\Scripts\python.exe" (
    echo  [1/4] Preparando o Python...
    python -m venv backend\.venv
    if errorlevel 1 (
        echo  ERRO: Python nao encontrado. Instale em python.org.
        pause
        exit /b 1
    )
    backend\.venv\Scripts\python.exe -m pip install --quiet --only-binary=:all: -r backend\requirements.txt pyinstaller
) else (
    echo  [1/4] Python ja preparado.
)

echo  [2/4] Exportando a interface...
pushd frontend
if not exist "node_modules" call npm install --no-audit --no-fund --silent
set PROSPECTOR_DESKTOP=1
call npx next build
if errorlevel 1 (
    popd
    echo  ERRO ao compilar a interface.
    pause
    exit /b 1
)
popd

echo  [3/4] Empacotando o aplicativo...
pushd backend
.venv\Scripts\python.exe -m PyInstaller packaging\Prospector.spec --noconfirm --clean
if errorlevel 1 (
    popd
    echo  ERRO ao empacotar o aplicativo.
    pause
    exit /b 1
)

REM  O instalador carrega a pasta do aplicativo dentro dele, entao so pode
REM  ser montado depois que o passo acima terminar.
echo  [4/4] Montando o instalador de arquivo unico...
.venv\Scripts\python.exe -m PyInstaller packaging\ProspectorSetup.spec --noconfirm --clean
if errorlevel 1 (
    popd
    echo  ERRO ao montar o instalador.
    pause
    exit /b 1
)
popd

echo.
echo  Pronto.
echo.
echo    Para dar a alguem:  backend\dist\ProspectorSetup.exe
echo    (arquivo unico - a pessoa da dois cliques e pronto)
echo.
echo    Para instalar aqui:  backend\dist\ProspectorSetup.exe
echo.
pause
