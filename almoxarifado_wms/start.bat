@echo off
cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo ERRO: ambiente virtual nao encontrado.
    echo Execute primeiro: py -m venv .venv
    pause
    exit /b 1
)

".venv\Scripts\python.exe" run_server.py
pause