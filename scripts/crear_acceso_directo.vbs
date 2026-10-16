Set oWS = WScript.CreateObject("WScript.Shell")
sLinkFile = oWS.SpecialFolders("Desktop") & "\Decretómetro 2.0.lnk"
Set oLink = oWS.CreateShortcut(sLinkFile)
oLink.TargetPath = "C:\Users\bornemanns\.gemini\antigravity-ide\scratch\decretometro_2.0\run_decretometro.bat"
oLink.WorkingDirectory = "C:\Users\bornemanns\.gemini\antigravity-ide\scratch\decretometro_2.0"
oLink.Description = "Iniciar Decretómetro 2.0"
oLink.Save
WScript.Echo "Acceso directo creado con exito en: " & sLinkFile
