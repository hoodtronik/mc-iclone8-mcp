# Run ELEVATED (one UAC prompt). Installs the iCloneMCP autostart plugin; optionally uninstalls AccuPOSE.
# CLAUDE-NOTE (2026-09-26, hoodtronik fork): Program Files\...\OpenPlugin needs admin; this is the only admin step —
# everything else loads from G:\_AI_Agents\mc-iclone8-mcp at runtime.
param([switch]$UninstallAccuPose)
$dst = "C:\Program Files\Reallusion\iClone 8\Bin64\OpenPlugin\iCloneMCP_Autostart"
New-Item -ItemType Directory -Force -Path $dst | Out-Null
Copy-Item -Force "G:\_AI_Agents\mc-iclone8-mcp\autostart\main.py" "$dst\main.py"
"installed: $dst\main.py" | Out-File -Append "$env:USERPROFILE\Desktop\icmcp_loader_log.txt"
if ($UninstallAccuPose) {
  $u = "C:\Program Files (x86)\InstallShield Installation Information\{DB3DD55D-7F3F-41B6-BE20-147C2B83AA8A}\setup.exe"
  Start-Process -FilePath $u -ArgumentList "-runfromtemp","-l0x0409","/z-uninstall" -Wait
}
