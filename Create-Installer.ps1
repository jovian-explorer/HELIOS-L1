<#
.SYNOPSIS
    HELIOS-L1 Windows System Installer
.DESCRIPTION
    Installs HELIOS-L1 on the current Windows user profile.
    Creates Start Menu and Desktop shortcuts with high-resolution icons.
#>

$ErrorActionPreference = "Stop"

$RootDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ExePath = Join-Path $RootDir "dist\HELIOS-L1\HELIOS-L1.exe"
$IconPath = Join-Path $RootDir "assets\helios.ico"

Write-Host "============================================================" -ForegroundColor Cyan
Write-Host " HELIOS-L1 Space Weather Suite: Windows Installer" -ForegroundColor Yellow
Write-Host "============================================================" -ForegroundColor Cyan

if (-not (Test-Path $ExePath)) {
    Write-Host "[!] Executable not found at: $ExePath" -ForegroundColor Red
    Write-Host "[*] Please run 'python build_installer.py' first." -ForegroundColor Yellow
    exit 1
}

Write-Host "[+] Found executable: $ExePath" -ForegroundColor Green

# 1. Desktop Shortcut
$WshShell = New-Object -ComObject WScript.Shell
$DesktopPath = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Desktop)
$DesktopShortcutPath = Join-Path $DesktopPath "HELIOS-L1.lnk"

$Shortcut = $WshShell.CreateShortcut($DesktopShortcutPath)
$Shortcut.TargetPath = $ExePath
$Shortcut.WorkingDirectory = (Split-Path -Parent $ExePath)
$Shortcut.Description = "HELIOS-L1: Heliophysical Exploration & L1 Space-weather Suite"
if (Test-Path $IconPath) {
    $Shortcut.IconLocation = "$IconPath,0"
}
$Shortcut.Save()
Write-Host "[+] Desktop shortcut created: $DesktopShortcutPath" -ForegroundColor Green

# 2. Start Menu Shortcut
$StartMenuPath = [System.Environment]::GetFolderPath([System.Environment+SpecialFolder]::Programs)
$HeliosStartFolder = Join-Path $StartMenuPath "HELIOS-L1"
if (-not (Test-Path $HeliosStartFolder)) {
    New-Item -ItemType Directory -Path $HeliosStartFolder -Force | Out-Null
}
$StartShortcutPath = Join-Path $HeliosStartFolder "HELIOS-L1.lnk"

$StartShortcut = $WshShell.CreateShortcut($StartShortcutPath)
$StartShortcut.TargetPath = $ExePath
$StartShortcut.WorkingDirectory = (Split-Path -Parent $ExePath)
$StartShortcut.Description = "HELIOS-L1: Heliophysical Exploration & L1 Space-weather Suite"
if (Test-Path $IconPath) {
    $StartShortcut.IconLocation = "$IconPath,0"
}
$StartShortcut.Save()
Write-Host "[+] Start Menu entry created: $StartShortcutPath" -ForegroundColor Green

# 3. Create Uninstaller script
$UninstallerPath = Join-Path $RootDir "Uninstall-HELIOS.ps1"
@"
Write-Host "[*] Removing HELIOS-L1 shortcuts..." -ForegroundColor Yellow
if (Test-Path '$DesktopShortcutPath') { Remove-Item -Path '$DesktopShortcutPath' -Force }
if (Test-Path '$HeliosStartFolder') { Remove-Item -Path '$HeliosStartFolder' -Recurse -Force }
Write-Host "[+] HELIOS-L1 shortcuts removed." -ForegroundColor Green
"@ | Out-File -FilePath $UninstallerPath -Encoding UTF8
Write-Host "[+] Uninstaller generated: $UninstallerPath" -ForegroundColor Green

Write-Host "`n============================================================" -ForegroundColor Cyan
Write-Host " Installation Complete! You can now launch HELIOS-L1" -ForegroundColor Green
Write-Host " from your Desktop shortcut, Start Menu, or by running:" -ForegroundColor Green
Write-Host " .\dist\HELIOS-L1\HELIOS-L1.exe" -ForegroundColor White
Write-Host "============================================================" -ForegroundColor Cyan
