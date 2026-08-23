@echo off
echo =========================================
echo Baue AI Metatagger EXE...
echo =========================================
python -m pyinstaller --noconsole --onedir --name "AI_Metatagger" Cockpit_V2.py

echo.
echo Kopiere config.json in den dist Ordner...
copy config.json dist\AI_Metatagger\config.json

echo.
echo =========================================
echo FERTIG! Deine EXE liegt in "dist\AI_Metatagger\"
echo =========================================
pause
