@echo off
echo 🚀 Iniciando ATLAS modo movil...

REM --- Backend ---
start cmd /k "echo 🔧 Backend && uvicorn app.main:app --reload --host 0.0.0.0 --port 8001"

REM --- Frontend ---
start cmd /k "echo 🎨 Frontend && cd frontend && npm run dev -- --host"

REM --- NGROK (frontend proxy) ---
start cmd /k "echo 🌐 Ngrok && C:\Users\Didago\ngrok.exe http 5173"

echo ✅ Todo levantado. Abre la URL de ngrok en tu celular.
