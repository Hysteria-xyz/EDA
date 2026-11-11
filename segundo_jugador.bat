@echo off
title EDA - Segundo Jugador
cd /d "%~dp0"
py -3.10 jugar.py %*
if %ERRORLEVEL% NEQ 0 (
    echo.
    echo Ocurrio un error al ejecutar el segundo cliente (Codigo: %ERRORLEVEL%)
    pause
)
