@echo off
REM Instala o Prospector para o usuario atual. Nao precisa de administrador.
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install.ps1"
