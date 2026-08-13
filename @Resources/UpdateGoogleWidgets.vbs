Option Explicit
Dim fso, root, script, shell, python, rm, command, rc
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
script = fso.BuildPath(root, "UpdateGoogleWidgets.py")
Set shell = CreateObject("WScript.Shell")
python = FindPython(shell, fso)
If python = "" Then WScript.Quit 3
command = """" & python & """ """ & script & """"
rc = shell.Run(command, 0, True)
If rc = 0 Then
  rm = """C:\Program Files\Rainmeter\Rainmeter.exe"""
  shell.Run rm & " !Refresh ""WindowsPorthexTheme\Calendar""", 0, True
  shell.Run rm & " !Refresh ""WindowsPorthexTheme\Email""", 0, False
End If

Function FindPython(sh, fs)
  Dim localApp, versions, version, candidate, exec
  localApp = sh.ExpandEnvironmentStrings("%LOCALAPPDATA%")
  versions = Array("Python313", "Python312", "Python311")
  For Each version In versions
    candidate = fs.BuildPath(localApp, "Programs\Python\" & version & "\python.exe")
    If fs.FileExists(candidate) Then FindPython = candidate: Exit Function
  Next
  On Error Resume Next
  Set exec = sh.Exec("cmd.exe /d /c where python.exe")
  If Err.Number = 0 Then
    candidate = Trim(Split(exec.StdOut.ReadAll, vbCrLf)(0))
    If fs.FileExists(candidate) Then FindPython = candidate: Exit Function
  End If
  On Error GoTo 0
  FindPython = ""
End Function
