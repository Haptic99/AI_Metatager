Set WshShell = CreateObject("WScript.Shell")
WshShell.CurrentDirectory = "F:\Jellyfin_AI_Cockpit"
WshShell.Run """C:\Program Files\Python313\python.exe"" Cockpit_V2.py", 0, False
