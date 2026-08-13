Option Explicit
Dim action, fso, root, settings, state, shell, current, nextValue, python, controller, command, rc
If WScript.Arguments.Count < 1 Then WScript.Quit 2
action = LCase(WScript.Arguments(0))
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
settings = fso.BuildPath(root, "UserSettings.inc")
state = fso.BuildPath(root, "UpdateState.inc")
Set shell = CreateObject("WScript.Shell")
If action = "toggle-auto" Then
  current = ReadKey(settings, "AutoUpdate", "0")
  If current = "1" Then nextValue = "0" Else nextValue = "1"
  ReplaceKey settings, "AutoUpdate", nextValue
  ReplaceKey state, "AutoUpdate", nextValue
  If nextValue = "1" Then ReplaceKey state, "AutoUpdateLabel", "ON" Else ReplaceKey state, "AutoUpdateLabel", "OFF"
  shell.Run """C:\Program Files\Rainmeter\Rainmeter.exe"" !Refresh ""WindowsPorthexTheme\Settings""", 0, False
ElseIf action = "profiles" Then
  python = FindPython(shell, fso)
  If python = "" Then shell.Popup "Python 3 is required for Porthex profiles.", 8, "Porthex settings", 48: WScript.Quit 3
  controller = fso.BuildPath(root, "WorkspaceController.py")
  command = Quote(python) & " " & Quote(controller) & " setup"
  rc = shell.Run(command, 0, True)
  If rc = 0 Then
    ReplaceKey state, "ProfileState", "READY"
    ReplaceKey state, "ProfileDetail", "Quiet / Work / Deep Focus are available."
    ReplaceKey state, "ProfileColor", "95,210,140,255"
  Else
    ReplaceKey state, "ProfileState", "SETUP ERROR"
    ReplaceKey state, "ProfileDetail", "Virtual desktop setup failed."
    ReplaceKey state, "ProfileColor", "184,104,88,255"
  End If
  shell.Run """C:\Program Files\Rainmeter\Rainmeter.exe"" !Refresh ""WindowsPorthexTheme\Settings""", 0, False
Else
  WScript.Quit 2
End If

Function Quote(value)
  Quote = """" & value & """"
End Function

Function ReadKey(path, key, fallback)
  Dim input, line
  ReadKey = fallback
  Set input = fso.OpenTextFile(path, 1, False)
  Do Until input.AtEndOfStream
    line = input.ReadLine
    If LCase(Left(line, Len(key) + 1)) = LCase(key & "=") Then ReadKey = Mid(line, Len(key) + 2): Exit Do
  Loop
  input.Close
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

Sub ReplaceKey(path, key, value)
  Dim input, text, re, output
  Set input = fso.OpenTextFile(path, 1, False)
  text = input.ReadAll
  input.Close
  Set re = New RegExp
  re.Global = True: re.MultiLine = True: re.Pattern = "^" & key & ".*$"
  text = re.Replace(text, key & "=" & value)
  Set output = fso.CreateTextFile(path, True, False)
  output.Write text
  output.Close
End Sub
