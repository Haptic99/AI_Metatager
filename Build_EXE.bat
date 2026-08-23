@echo off
echo =========================================
echo Baue AI Metatagger EXE...
echo =========================================
set PYTHONPATH=%~dp0src
python -m pyinstaller --noconsole --onedir --name "AI_Metatagger" src\ai_metatagger\main.py

echo.
echo Kopiere config.json in den dist Ordner...
copy data\config.json dist\AI_Metatagger\config.json

echo.
echo =========================================
echo FERTIG! Deine EXE liegt in "dist\AI_Metatagger\"
echo =========================================
pause
