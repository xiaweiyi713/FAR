$ErrorActionPreference = "Continue"

$Distro = "Ubuntu-24.04"
$TrainingUser = "wenyao"
$Log = "C:\Scripts\keep-wsl-training-online.log"

New-Item -ItemType Directory -Force -Path C:\Scripts | Out-Null

function Write-Log($Message) {
  Add-Content -Path $Log -Value ("{0:s} {1}" -f (Get-Date), $Message)
}

Write-Log "Starting WSL training keepalive."

while ($true) {
  try {
    # Linger is required in addition to keeping the WSL VM alive. Without it,
    # systemd can interrupt detached tmux panes shortly after the last SSH
    # session for the training user disconnects.
    wsl.exe -d $Distro -u root -- bash -lc "loginctl enable-linger $TrainingUser; systemctl start tailscaled ssh; systemctl is-active tailscaled ssh; tailscale ip -4 || true" 2>&1 |
      ForEach-Object { Write-Log $_ }

    # This blocking root process keeps the WSL VM online. The linger setting
    # above independently keeps the training user's systemd manager alive.
    wsl.exe -d $Distro -u root -- bash -lc "while true; do sleep 3600; done"
  } catch {
    Write-Log ("Keepalive loop error: " + $_.Exception.Message)
  }

  Start-Sleep -Seconds 10
}
