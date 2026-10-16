# Run ELEVATED (one UAC prompt). Installs the iCloneMCP autostart plugin; optionally uninstalls AccuPOSE.
# CLAUDE-NOTE (2026-09-26, hoodtronik fork): Program Files\...\OpenPlugin needs admin; this is the only admin step —
# everything else loads from G:\_AI_Agents\mc-iclone8-mcp at runtime.
param([switch]$UninstallAccuPose)
$dst = "C:\Program Files\Reallusion\iClone 8\Bin64\OpenPlugin\iCloneMCP_Autostart"
New-Item -ItemType Directory -Force -Path $dst | Out-Null
# CLAUDE-NOTE (2026-10-16): copy from this checkout instead of a hardcoded G:\ path so any machine can install;
# the plugin finds the fork at runtime via the MC_ICLONE8_MCP_DIR user env var (persisted below).
$fork = Split-Path -Parent $PSScriptRoot
Copy-Item -Force (Join-Path $fork "autostart\main.py") "$dst\main.py"
[Environment]::SetEnvironmentVariable("MC_ICLONE8_MCP_DIR", $fork, "User")
"installed: $dst\main.py" | Out-File -Append "$env:USERPROFILE\Desktop\icmcp_loader_log.txt"
if ($UninstallAccuPose) {
  $u = "C:\Program Files (x86)\InstallShield Installation Information\{DB3DD55D-7F3F-41B6-BE20-147C2B83AA8A}\setup.exe"
  Start-Process -FilePath $u -ArgumentList "-runfromtemp","-l0x0409","/z-uninstall" -Wait
}
