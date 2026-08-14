Option Explicit
Dim mode, idx, label, base, indicator, fso, root, profile, topbar, field, controller, shell, rm, python, command, rc
If WScript.Arguments.Count < 1 Then WScript.Quit 2
mode = LCase(WScript.Arguments(0))
Select Case mode
  Case "quiet": idx = "1": label = "QUIET": base = "188": indicator = "18"
  Case "work": idx = "2": label = "WORK": base = "208": indicator = "47"
  Case "focus": idx = "3": label = "DEEP FOCUS": base = "160": indicator = "76"
  Case Else: WScript.Quit 2
End Select
Set fso = CreateObject("Scripting.FileSystemObject")
root = fso.GetParentFolderName(WScript.ScriptFullName)
profile = fso.BuildPath(root, "Profile.inc")
topbar = fso.BuildPath(fso.BuildPath(fso.GetParentFolderName(root), "TopBar"), "TopBar.ini")
field = fso.BuildPath(fso.BuildPath(fso.GetParentFolderName(root), "Field"), "Field.ini")
controller = fso.BuildPath(root, "WorkspaceController.py")
Set shell = CreateObject("WScript.Shell")
python = FindPython(shell, fso)
If python = "" Then
  shell.Popup "Python 3 is required for Porthex profiles. Install Python, then open Porthex Settings and run profile setup.", 8, "Porthex profiles", 48
  WScript.Quit 3
End If
command = Quote(python) & " " & Quote(controller) & " switch " & idx
rc = shell.Run(command, 0, True)
If rc <> 0 Then
  shell.Popup "The Windows virtual desktop switch failed. Open Porthex Settings and run profile setup.", 8, "Porthex profiles", 48
  WScript.Quit rc
End If
ReplaceKey profile, "ProfileIndex", idx
ReplaceKey profile, "ProfileName", label
ReplaceKey profile, "ProfileIndicatorX", indicator
ReplaceKey profile, "ProfileFieldBase", base
ReplaceKey topbar, "ProfileIndex", idx
ReplaceKey topbar, "ProfileName", label
ReplaceKey topbar, "ProfileIndicatorX", indicator
ReplaceKey field, "ProfileFieldBase", base
rm = Quote("C:\Program Files\Rainmeter\Rainmeter.exe")
shell.Run rm & " !Refresh ""WindowsPorthexTheme\TopBar""", 0, True
shell.Run rm & " !Refresh ""WindowsPorthexTheme\Field""", 0, False

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

Sub ReplaceKey(path, key, value)
  Dim input, text, re, out
  Set input = fso.OpenTextFile(path, 1, False)
  text = input.ReadAll
  input.Close
  Set re = New RegExp
  re.Global = True
  re.MultiLine = True
  re.Pattern = "^" & key & ".*$"
  text = re.Replace(text, key & "=" & value)
  Set out = fso.CreateTextFile(path, True, False)
  out.Write text
  out.Close
End Sub
