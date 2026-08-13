Option Explicit
Dim action, fso, root, script, shell, python, command
If WScript.Arguments.Count < 1 Then WScript.Quit 2
action = LCase(WScript.Arguments(0))
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
script = fso.BuildPath(root, "UpdateManager.py")
Set shell = CreateObject("WScript.Shell")
python = FindPython(shell, fso)
If python = "" Then
  shell.Popup "Python 3 is required for theme updates.", 8, "Porthex settings", 48
  WScript.Quit 3
End If
command = Quote(python) & " " & Quote(script) & " " & action
shell.Run command, 0, False

Function Quote(value)
  Quote = """" & value & """"
End Function

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
