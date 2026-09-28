@echo off
title Decretometro 2.0
cd /d C:\Users\bornemanns\.gemini\antigravity-ide\scratch\decretometro_2.0
echo Iniciando Decretometro 2.0...

:: Buscar puerto libre entre 8501 y 8510
set PORT=
for /L %%P in (8501,1,8510) do (
    if not defined PORT (
        netstat -an | find "%%P" | find "LISTENING" >nul 2>&1
        if errorlevel 1 set PORT=%%P
    )
)
if not defined PORT set PORT=8505

echo Usando puerto: %PORT%
streamlit run Inicio.py --server.port %PORT%
