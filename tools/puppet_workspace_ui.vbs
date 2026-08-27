Set Shell = CreateObject("WScript.Shell")
Set Fso = CreateObject("Scripting.FileSystemObject")
ScriptDir = Fso.GetParentFolderName(WScript.ScriptFullName)
Command = "cmd.exe /c """ & ScriptDir & "\puppet_workspace_ui.cmd"""
Shell.Run Command, 0, False

