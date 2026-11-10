@echo off

cd /d D:\Apps\Tuburon\ATLAS

echo ======================================
echo      Iniciando ATLAS
echo ======================================
echo.

wt ^
new-tab -d "D:\Apps\Tuburon\ATLAS" cmd /k "call .venv\Scripts\activate.bat && python -B -m app.dev_launcher" ^
; split-pane -H -d "D:\Apps\Tuburon\ATLAS\frontend" cmd /k "npm run dev -- --host" ^
; split-pane -V -d "D:\Apps\Tuburon\ATLAS" cmd /k "call .venv\Scripts\activate.bat && python -m devtools.launcher.launcher" ^
; new-tab --title "Notifications" -d "D:\Apps\Tuburon\ATLAS" cmd /k ".venv\Scripts\python.exe -B -m app.bot_console notifications" ^
; split-pane -H --title "Incidents" -d "D:\Apps\Tuburon\ATLAS" cmd /k ".venv\Scripts\python.exe -B -m app.bot_console incidents" ^
; split-pane -V --title "Editorial" -d "D:\Apps\Tuburon\ATLAS" cmd /k ".venv\Scripts\python.exe -B -m app.bot_console editorial"

echo.
echo ✅ Todo iniciado.
