Write-Host "[*] Removing HELIOS-L1 shortcuts..." -ForegroundColor Yellow
if (Test-Path 'C:\Users\AGY-VCO\Desktop\HELIOS-L1.lnk') { Remove-Item -Path 'C:\Users\AGY-VCO\Desktop\HELIOS-L1.lnk' -Force }
if (Test-Path 'C:\Users\AGY-VCO\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\HELIOS-L1') { Remove-Item -Path 'C:\Users\AGY-VCO\AppData\Roaming\Microsoft\Windows\Start Menu\Programs\HELIOS-L1' -Recurse -Force }
Write-Host "[+] HELIOS-L1 shortcuts removed." -ForegroundColor Green
