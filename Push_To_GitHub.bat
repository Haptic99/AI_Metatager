@echo off
cd /d "F:\Jellyfin_AI_Cockpit"
echo ========================================
echo   Jellyfin AI Cockpit - GitHub Push
echo ========================================
echo.
echo Entferne evtl. blockierte Git-Sperren...
if exist ".git\index.lock" del /F /Q ".git\index.lock"

echo Lade Dateien hoch...
git add -A
git commit -m "Auto-Commit durch Benutzer (Git_Push.bat)"
git push

echo.
echo ========================================
echo   Erfolgreich abgeschlossen!
echo ========================================
pause
