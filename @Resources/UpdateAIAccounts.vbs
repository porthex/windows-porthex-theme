Option Explicit
Dim fso, root, script, shell, python, rm, rc
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
script = fso.BuildPath(root, "UpdateAIAccounts.py")
Set shell = CreateObject("WScript.Shell")
python = shell.ExpandEnvironmentStrings("%LOCALAPPDATA%\hermes\hermes-agent\venv\Scripts\python.exe")
If Not fso.FileExists(python) Then WScript.Quit 3
rc = shell.Run("""" & python & """ """ & script & """", 0, True)
If rc = 0 Then
  rm = """C:\Program Files\Rainmeter\Rainmeter.exe"""
  shell.Run rm & " !Refresh ""WindowsPorthexTheme\AIAccounts""", 0, False
End If
