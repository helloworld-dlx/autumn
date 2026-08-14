Option Explicit

Dim shell
Set shell = CreateObject("WScript.Shell")
WScript.Quit shell.Run(shell.ExpandEnvironmentStrings("%ComSpec%") & " /d /c """"D:\JarvisWorkspace\JarvisRunner\run-runner.cmd""""", 0, True)
