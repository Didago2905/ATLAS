@echo off

cd /d D:\Apps\Tuburon\ATLAS

echo ======================================
echo      Iniciando ATLAS
echo ======================================
echo.

wt ^
new-tab -d "D:\Apps\Tuburon\ATLAS" cmd /k "call .venv\Scripts\activate.bat && python -B -m app.dev_launcher" ^
; split-pane -H -d "D:\Apps\Tuburon\ATLAS\frontend" cmd /k "npm run dev -- --host" ^
; split-pane -V -d "D:\Apps\Tuburon\ATLAS" cmd /k "call .venv\Scripts\activate.bat && python -m devtools.launcher.launcher"

echo.
echo ✅ Todo iniciado.
