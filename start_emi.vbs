' ═══════════════════════════════════════════════════════
' start_emi.vbs — Launches Emi Assistant with NO console window
' Run this file directly, or let install_startup.bat add it to
' Windows Startup so Emi starts automatically every boot.
' ═══════════════════════════════════════════════════════
Option Explicit

Dim Shell, FSO, appDir, pythonwExe, cmd

Set Shell = CreateObject("WScript.Shell")
Set FSO   = CreateObject("Scripting.FileSystemObject")
appDir    = Left(WScript.ScriptFullName, InStrRev(WScript.ScriptFullName, "\") - 1)

' Prefer pythonw.exe (silently runs Python with no console window).
' Walk through common install paths; fall back to whatever is on PATH.
Dim candidates(4)
candidates(0) = Shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python312\pythonw.exe"
candidates(1) = Shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python311\pythonw.exe"
candidates(2) = Shell.ExpandEnvironmentStrings("%LOCALAPPDATA%") & "\Programs\Python\Python310\pythonw.exe"
candidates(3) = "C:\Python312\pythonw.exe"
candidates(4) = "C:\Python311\pythonw.exe"

pythonwExe = "pythonw"   ' fallback: rely on PATH

Dim i
For i = 0 To 4
    If FSO.FileExists(candidates(i)) Then
        pythonwExe = candidates(i)
        Exit For
    End If
Next

' Launch launch.py with pythonw so there is zero console window.
' Window style 0 = completely hidden, False = don't wait.
cmd = """" & pythonwExe & """ """ & appDir & "\launch.py"""

Shell.Run cmd, 0, False

Set Shell = Nothing
Set FSO   = Nothing
