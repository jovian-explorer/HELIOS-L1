"""
HELIOS-L1 Standalone Windows Setup Wizard and Installer.
Installs HELIOS-L1 into the user profile (AppData/Local/Programs or Program Files),
extracts all binaries, runtime libraries, and assets,
creates Windows Desktop and Start Menu shortcuts with icons,
registers the uninstaller in Windows Add/Remove Programs,
and provides an option to launch HELIOS-L1 immediately.
"""
import os
import sys
import shutil
import zipfile
import winreg
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading
import subprocess

APP_NAME = "HELIOS-L1"
APP_FULL_NAME = "Heliophysical Exploration, Lagrange-1 Interplanetary Observation & Space-weather Suite"
APP_VERSION = "1.2.0"
APP_PUBLISHER = "Dr. Keshav Aggarwal (SPL, VSSC / ISRO & IIT Indore)"

def get_default_install_dir() -> Path:
    # Use user profile root (e.g. C:\Users\<Username>\HELIOS-L1)
    # This prevents Windows Store / UWP filesystem redirection and guarantees clean desktop shortcuts
    home_dir = Path(os.environ.get("USERPROFILE", str(Path.home())))
    return home_dir / APP_NAME

def get_payload_path() -> Path:
    """Find bundled payload.zip in PyInstaller bundle or script directory."""
    if getattr(sys, "frozen", False):
        base = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
        candidate = base / "payload.zip"
        if candidate.exists():
            return candidate
        # Check next to exe
        candidate = Path(sys.executable).parent / "payload.zip"
        if candidate.exists():
            return candidate
        # Check dist directory
        candidate = Path(sys.executable).parent / "dist" / "HELIOS-L1-v1.0-Windows-x64.zip"
        if candidate.exists():
            return candidate
    else:
        root = Path(__file__).resolve().parent
        for c in [
            root / "payload.zip",
            root / "dist" / "payload.zip",
            root / "dist" / "HELIOS-L1-v1.0-Windows-x64.zip"
        ]:
            if c.exists():
                return c
    return Path("payload.zip")

def create_windows_shortcut(target_exe: str, shortcut_path: str, working_dir: str, icon_path: str = None, description: str = ""):
    """Create Windows shortcut (.lnk) via PowerShell COM script."""
    cmd = [
        "powershell", "-NoProfile", "-NonInteractive", "-Command",
        f"$ws = New-Object -ComObject WScript.Shell; "
        f"$s = $ws.CreateShortcut('{shortcut_path}'); "
        f"$s.TargetPath = '{target_exe}'; "
        f"$s.WorkingDirectory = '{working_dir}'; "
        f"$s.Description = '{description}'; "
    ]
    if icon_path and os.path.exists(icon_path):
        cmd[-1] += f"$s.IconLocation = '{icon_path},0'; "
    cmd[-1] += "$s.Save();"

    subprocess.run(cmd, creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)

def register_uninstaller(install_dir: Path, uninstaller_bat: Path, icon_path: Path):
    """Register HELIOS-L1 in Windows Add/Remove Programs (Registry HKCU)."""
    reg_path = r"Software\Microsoft\Windows\CurrentVersion\Uninstall\HELIOS-L1"
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, reg_path) as key:
            winreg.SetValueEx(key, "DisplayName", 0, winreg.REG_SZ, f"HELIOS-L1 Space Weather Suite v{APP_VERSION}")
            winreg.SetValueEx(key, "DisplayVersion", 0, winreg.REG_SZ, APP_VERSION)
            winreg.SetValueEx(key, "Publisher", 0, winreg.REG_SZ, APP_PUBLISHER)
            winreg.SetValueEx(key, "InstallLocation", 0, winreg.REG_SZ, str(install_dir))
            winreg.SetValueEx(key, "UninstallString", 0, winreg.REG_SZ, f'"{uninstaller_bat}"')
            if icon_path.exists():
                winreg.SetValueEx(key, "DisplayIcon", 0, winreg.REG_SZ, str(icon_path))
            winreg.SetValueEx(key, "NoModify", 0, winreg.REG_DWORD, 1)
            winreg.SetValueEx(key, "NoRepair", 0, winreg.REG_DWORD, 1)
    except Exception as e:
        print(f"[!] Registry registration warning: {e}")

def perform_installation(
    target_dir: Path,
    desktop_shortcut: bool,
    start_menu_shortcut: bool,
    progress_callback=None
):
    """Core installation logic."""
    payload_zip = get_payload_path()
    if not payload_zip.exists():
        raise FileNotFoundError(f"Installation payload not found at: {payload_zip}")

    target_dir.mkdir(parents=True, exist_ok=True)

    # 1. Extract files from zip
    if progress_callback:
        progress_callback(10, "Extracting scientific libraries and binaries...")

    with zipfile.ZipFile(payload_zip, "r") as z:
        total_files = len(z.infolist())
        for i, item in enumerate(z.infolist()):
            # Handle root folder prefix in zip if any (e.g. HELIOS-L1/...)
            parts = Path(item.filename).parts
            if len(parts) > 1 and parts[0] == "HELIOS-L1":
                rel_parts = parts[1:]
            else:
                rel_parts = parts

            if not rel_parts:
                continue

            dest_path = target_dir.joinpath(*rel_parts)
            if item.is_dir():
                dest_path.mkdir(parents=True, exist_ok=True)
            else:
                dest_path.parent.mkdir(parents=True, exist_ok=True)
                with z.open(item) as src, open(dest_path, "wb") as dst:
                    shutil.copyfileobj(src, dst)

            if progress_callback and i % 25 == 0:
                pct = 10 + int((i / total_files) * 65)
                progress_callback(pct, f"Extracting: {rel_parts[-1]}")

    exe_path = target_dir / "HELIOS-L1.exe"
    icon_path = target_dir / "assets" / "helios.ico"
    if not icon_path.exists():
        # Check adjacent assets
        candidate_icon = target_dir / "_internal" / "assets" / "helios.ico"
        if candidate_icon.exists():
            icon_path = candidate_icon

    # 2. Desktop Shortcut
    if desktop_shortcut and exe_path.exists():
        if progress_callback:
            progress_callback(80, "Creating Desktop shortcut...")
        desktop_dir = Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop"
        shortcut_file = desktop_dir / "HELIOS-L1.lnk"
        create_windows_shortcut(
            str(exe_path),
            str(shortcut_file),
            str(target_dir),
            str(icon_path) if icon_path.exists() else None,
            "HELIOS-L1: Space Weather & L1 Heliophysics Suite"
        )

    # 3. Start Menu Shortcut
    if start_menu_shortcut and exe_path.exists():
        if progress_callback:
            progress_callback(88, "Creating Start Menu entry...")
        programs_dir = Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "HELIOS-L1"
        programs_dir.mkdir(parents=True, exist_ok=True)
        start_shortcut_file = programs_dir / "HELIOS-L1.lnk"
        create_windows_shortcut(
            str(exe_path),
            str(start_shortcut_file),
            str(target_dir),
            str(icon_path) if icon_path.exists() else None,
            "HELIOS-L1: Space Weather & L1 Heliophysics Suite"
        )

    # 4. Generate Uninstaller
    if progress_callback:
        progress_callback(94, "Configuring uninstaller & registration...")

    uninstaller_bat = target_dir / "Uninstall-HELIOS.bat"
    desktop_shortcut_path = (Path(os.environ.get("USERPROFILE", str(Path.home()))) / "Desktop" / "HELIOS-L1.lnk")
    start_menu_folder = (Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "HELIOS-L1")

    uninstall_content = f"""@echo off
title Uninstall HELIOS-L1
echo ================================================================
echo  HELIOS-L1 Space Weather Suite Uninstaller
echo ================================================================
echo.
echo Removing shortcuts...
if exist "{desktop_shortcut_path}" del /f /q "{desktop_shortcut_path}"
if exist "{start_menu_folder}" rd /s /q "{start_menu_folder}"

echo Removing registry entries...
reg delete "HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Uninstall\\HELIOS-L1" /f >nul 2>&1

echo.
echo HELIOS-L1 shortcuts and registrations have been removed.
echo To completely remove files, you can delete this folder:
echo {target_dir}
echo.
pause
"""
    with open(uninstaller_bat, "w", encoding="utf-8") as f:
        f.write(uninstall_content)

    # 5. Register in Windows Settings / Control Panel
    register_uninstaller(target_dir, uninstaller_bat, icon_path)

    if progress_callback:
        progress_callback(100, "Installation complete!")


class InstallerWizardGUI:
    """Modern Tkinter Setup Wizard for HELIOS-L1."""

    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title(f"{APP_NAME} Setup - Windows Installer")
        self.root.geometry("640x480")
        self.root.resizable(False, False)
        self.root.configure(bg="#0b1329")

        self.target_dir_var = tk.StringVar(value=str(get_default_install_dir()))
        self.desktop_shortcut_var = tk.BooleanVar(value=True)
        self.start_shortcut_var = tk.BooleanVar(value=True)
        self.launch_after_var = tk.BooleanVar(value=True)

        self.setup_styles()
        self.build_ui()

    def setup_styles(self):
        style = ttk.Style()
        style.theme_use("clam")
        style.configure("TProgressbar", thickness=16, troughcolor="#111e3e", background="#38bdf8")

    def build_ui(self):
        # Header banner
        header_frame = tk.Frame(self.root, bg="#060a12", height=85, padx=20, pady=15)
        header_frame.pack(fill="x", side="top")

        title_lbl = tk.Label(
            header_frame,
            text=f"☀️ {APP_NAME} Space Weather Suite",
            font=("Segoe UI", 16, "bold"),
            fg="#38bdf8",
            bg="#060a12"
        )
        title_lbl.pack(anchor="w")

        sub_lbl = tk.Label(
            header_frame,
            text="Sun-Earth L1 Lagrange Multi-Mission Heliophysical Science Platform",
            font=("Segoe UI", 9),
            fg="#94a3b8",
            bg="#060a12"
        )
        sub_lbl.pack(anchor="w", pady=(3, 0))

        # Main Body
        body_frame = tk.Frame(self.root, bg="#0b1329", padx=25, pady=18)
        body_frame.pack(fill="both", expand=True)

        info_lbl = tk.Label(
            body_frame,
            text=f"Setup will install {APP_NAME} v{APP_VERSION} on your computer.\n"
                 "Select destination folder and desktop options below:",
            font=("Segoe UI", 10),
            fg="#e2e8f0",
            bg="#0b1329",
            justify="left"
        )
        info_lbl.pack(anchor="w", pady=(0, 15))

        # Directory selection
        dir_frame = tk.LabelFrame(
            body_frame,
            text=" Installation Directory ",
            font=("Segoe UI", 9, "bold"),
            fg="#38bdf8",
            bg="#0b1329",
            padx=12,
            pady=10
        )
        dir_frame.pack(fill="x", pady=(0, 15))

        dir_entry = tk.Entry(
            dir_frame,
            textvariable=self.target_dir_var,
            font=("Consolas", 9),
            bg="#111e3e",
            fg="#f8fafc",
            insertbackground="#38bdf8",
            relief="flat",
            bd=5
        )
        dir_entry.pack(side="left", fill="x", expand=True, padx=(0, 8))

        browse_btn = tk.Button(
            dir_frame,
            text="Browse...",
            command=self.browse_dir,
            font=("Segoe UI", 9),
            bg="#1e293b",
            fg="#e2e8f0",
            activebackground="#334155",
            activeforeground="#ffffff",
            relief="flat",
            padx=10
        )
        browse_btn.pack(side="right")

        # Options
        opt_frame = tk.LabelFrame(
            body_frame,
            text=" Installation Options ",
            font=("Segoe UI", 9, "bold"),
            fg="#38bdf8",
            bg="#0b1329",
            padx=12,
            pady=8
        )
        opt_frame.pack(fill="x", pady=(0, 15))

        cb_desktop = tk.Checkbutton(
            opt_frame,
            text="Create Desktop Shortcut",
            variable=self.desktop_shortcut_var,
            font=("Segoe UI", 9),
            fg="#f1f5f9",
            bg="#0b1329",
            selectcolor="#111e3e",
            activebackground="#0b1329",
            activeforeground="#38bdf8"
        )
        cb_desktop.pack(anchor="w")

        cb_start = tk.Checkbutton(
            opt_frame,
            text="Create Windows Start Menu Program Group",
            variable=self.start_shortcut_var,
            font=("Segoe UI", 9),
            fg="#f1f5f9",
            bg="#0b1329",
            selectcolor="#111e3e",
            activebackground="#0b1329",
            activeforeground="#38bdf8"
        )
        cb_start.pack(anchor="w")

        cb_launch = tk.Checkbutton(
            opt_frame,
            text="Launch HELIOS-L1 immediately after installation",
            variable=self.launch_after_var,
            font=("Segoe UI", 9),
            fg="#f1f5f9",
            bg="#0b1329",
            selectcolor="#111e3e",
            activebackground="#0b1329",
            activeforeground="#38bdf8"
        )
        cb_launch.pack(anchor="w")

        # Progress bar
        self.progress_bar = ttk.Progressbar(body_frame, style="TProgressbar", mode="determinate")
        self.progress_bar.pack(fill="x", pady=(0, 5))

        self.status_lbl = tk.Label(
            body_frame,
            text="Ready to install.",
            font=("Segoe UI", 8),
            fg="#94a3b8",
            bg="#0b1329"
        )
        self.status_lbl.pack(anchor="w")

        # Bottom Bar
        bottom_frame = tk.Frame(self.root, bg="#060a12", height=55, padx=20, pady=12)
        bottom_frame.pack(fill="x", side="bottom")

        self.install_btn = tk.Button(
            bottom_frame,
            text="Install Now",
            command=self.start_install,
            font=("Segoe UI", 10, "bold"),
            bg="#0284c7",
            fg="#ffffff",
            activebackground="#0369a1",
            activeforeground="#ffffff",
            relief="flat",
            padx=20,
            pady=4,
            cursor="hand2"
        )
        self.install_btn.pack(side="right", padx=(8, 0))

        self.cancel_btn = tk.Button(
            bottom_frame,
            text="Cancel",
            command=self.root.destroy,
            font=("Segoe UI", 10),
            bg="#1e293b",
            fg="#94a3b8",
            activebackground="#334155",
            activeforeground="#ffffff",
            relief="flat",
            padx=14,
            pady=4
        )
        self.cancel_btn.pack(side="right")

    def browse_dir(self):
        chosen = filedialog.askdirectory(initialdir=self.target_dir_var.get())
        if chosen:
            self.target_dir_var.set(chosen)

    def start_install(self):
        self.install_btn.config(state="disabled")
        self.cancel_btn.config(state="disabled")
        target_dir = Path(self.target_dir_var.get())

        thread = threading.Thread(target=self._run_install_thread, args=(target_dir,))
        thread.daemon = True
        thread.start()

    def _run_install_thread(self, target_dir: Path):
        def update_ui(pct, status_text):
            self.root.after(0, lambda: self._update_progress(pct, status_text))

        try:
            perform_installation(
                target_dir=target_dir,
                desktop_shortcut=self.desktop_shortcut_var.get(),
                start_menu_shortcut=self.start_shortcut_var.get(),
                progress_callback=update_ui
            )
            self.root.after(0, lambda: self._on_install_success(target_dir))
        except Exception as e:
            self.root.after(0, lambda: self._on_install_failure(str(e)))

    def _update_progress(self, pct: int, status_text: str):
        self.progress_bar["value"] = pct
        self.status_lbl.config(text=status_text)

    def _on_install_success(self, target_dir: Path):
        self.progress_bar["value"] = 100
        self.status_lbl.config(text="Installation Complete!", fg="#10b981")
        self.install_btn.config(text="Finish", state="normal", command=self._finish_and_launch)
        self.cancel_btn.config(state="disabled")

        messagebox.showinfo(
            "HELIOS-L1 Setup",
            f"HELIOS-L1 v{APP_VERSION} has been successfully installed!\n\n"
            f"Installed Location:\n{target_dir}\n\n"
            "Shortcuts have been created on your Desktop and Start Menu."
        )

    def _on_install_failure(self, err: str):
        self.status_lbl.config(text=f"Error: {err}", fg="#f43f5e")
        self.install_btn.config(state="normal", text="Retry")
        self.cancel_btn.config(state="normal")
        messagebox.showerror("Installation Error", f"Failed to complete installation:\n{err}")

    def _finish_and_launch(self):
        target_dir = Path(self.target_dir_var.get())
        exe_path = target_dir / "HELIOS-L1.exe"
        if self.launch_after_var.get() and exe_path.exists():
            subprocess.Popen([str(exe_path)], cwd=str(target_dir))
        self.root.destroy()


def main():
    if "--silent" in sys.argv or "/S" in sys.argv:
        target_dir = get_default_install_dir()
        print(f"[*] Silent installation to: {target_dir}")
        perform_installation(target_dir, desktop_shortcut=True, start_menu_shortcut=True)
        print("[+] Installation complete.")
        return

    root = tk.Tk()
    app = InstallerWizardGUI(root)
    root.mainloop()

if __name__ == "__main__":
    main()
