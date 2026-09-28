Set oWS = WScript.CreateObject("WScript.Shell")
sLinkFile = oWS.SpecialFolders("Desktop") & "\Decretómetro.lnk"
Set oLink = oWS.CreateShortcut(sLinkFile)
oLink.TargetPath = "C:\Users\bornemanns\.gemini\antigravity-ide\scratch\decretometro\run_decretometro.bat"
oLink.WorkingDirectory = "C:\Users\bornemanns\.gemini\antigravity-ide\scratch\decretometro"
oLink.Description = "Abrir Sistema Decretometro"
oLink.Save
