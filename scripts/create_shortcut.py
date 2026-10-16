import os
import subprocess

desktop = os.path.join(os.environ['USERPROFILE'], 'Desktop')
target = r'c:\Users\bornemanns\.gemini\antigravity-ide\scratch\decretometro_2.0\run_decretometro.bat'
workdir = r'c:\Users\bornemanns\.gemini\antigravity-ide\scratch\decretometro_2.0'
shortcut_path = os.path.join(desktop, 'Decretómetro 2.0.lnk')

# Remove any malformed shortcuts
for fname in os.listdir(desktop):
    if 'Decret' in fname and '2.0' in fname and fname.endswith('.lnk'):
        try:
            os.remove(os.path.join(desktop, fname))
            print(f"Eliminado acceso anterior: {fname}")
        except:
            pass

vbs_content = f'''Set oWS = WScript.CreateObject("WScript.Shell")
sLinkFile = "{shortcut_path}"
Set oLink = oWS.CreateShortcut(sLinkFile)
oLink.TargetPath = "{target}"
oLink.WorkingDirectory = "{workdir}"
oLink.Description = "Decretometro 2.0 - Sistema Bimonetario"
oLink.Save
'''

vbs_temp = 'temp_shortcut.vbs'
with open(vbs_temp, 'w', encoding='latin-1') as f:
    f.write(vbs_content)

subprocess.run(['cscript', '//nologo', vbs_temp], check=True)
if os.path.exists(vbs_temp):
    os.remove(vbs_temp)

print("Acceso directo creado con exito en:", shortcut_path)
