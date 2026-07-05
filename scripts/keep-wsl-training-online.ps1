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
    # the training user's systemd services stop after the last SSH session
    # disconnects. Formal jobs run as user services rather than SSH-owned panes.
    wsl.exe -d $Distro -u root -- bash -lc "loginctl enable-linger $TrainingUser; systemctl start tailscaled ssh; systemctl is-active tailscaled ssh; tailscale ip -4 || true" 2>&1 |
      ForEach-Object { Write-Log $_ }

    # This blocking root process keeps the WSL VM online. While the explicit
    # D:-backed authorization marker exists, it also repairs accidental
    # stop/disable operations on the two formal RAMDocs services. The marker is
    # removed automatically as soon as the suite manifest exists.
    wsl.exe -d $Distro -u root -- bash -lc 'while true; do /mnt/d/FAR-tools/watch_windows_ramdocs_services.sh; sleep 15; done'
  } catch {
    Write-Log ("Keepalive loop error: " + $_.Exception.Message)
  }

  Start-Sleep -Seconds 10
}
