import os
import ctypes
import subprocess
from pathlib import Path

def update_shortcut():
    desktop = Path(os.environ.get("USERPROFILE", "C:/Users/AGY-VCO")) / "Desktop"
    shortcut_file = desktop / "HELIOS-L1.lnk"
    
    install_dir = Path(os.environ.get("USERPROFILE", "C:/Users/AGY-VCO")) / "HELIOS-L1"
    target_exe = install_dir / "HELIOS-L1.exe"
    icon_file = install_dir / "assets" / "helios.ico"
    
    if not icon_file.exists():
        fallback_ico = Path(__file__).resolve().parent.parent / "assets" / "helios.ico"
        if fallback_ico.exists():
            icon_file = fallback_ico

    print(f"[*] Updating desktop shortcut: {shortcut_file}")
    print(f"    Target: {target_exe}")
    print(f"    Icon:   {icon_file}")

    ps_code = f"""
$ws = New-Object -ComObject WScript.Shell
$s = $ws.CreateShortcut('{str(shortcut_file)}')
$s.TargetPath = '{str(target_exe)}'
$s.WorkingDirectory = '{str(install_dir)}'
$s.Description = 'HELIOS-L1 Space Weather Suite'
$s.IconLocation = '{str(icon_file)},0'
$s.Save()
"""
    cmd = ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", ps_code]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode == 0:
        print("[+] Shortcut successfully written with new clean icon location!")
    else:
        print(f"[-] PowerShell error: {res.stderr}")

    # Notify Windows Shell of association / icon change
    try:
        SHCNE_ASSOCCHANGED = 0x08000000
        SHCNF_IDLIST = 0x0000
        ctypes.windll.shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None)
        print("[+] Windows Shell notified to refresh icon cache (SHChangeNotify).")
    except Exception as e:
        print(f"[-] Shell notification warning: {e}")

if __name__ == "__main__":
    update_shortcut()
