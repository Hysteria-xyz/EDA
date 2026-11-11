@echo off
cd /d "%~dp0"
py -3.10 jugar.py %*
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Ocurrio un error al ejecutar jugar.py (Codigo: %ERRORLEVEL%)
    pause
)
