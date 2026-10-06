# nuc-monitor for linux
Web dashboard (Flask, port 8080) for a Linux home server:

- **Hardware**: CPU temperature & usage chart, GPU usage, RAM and disk status.
- **Torrent**: add / pause / remove downloads through aria2c JSON-RPC (`http://127.0.0.1:6800/jsonrpc`).
- **Services**: top processes by CPU / RAM.
- **Manage** (requires login with an SSH account of the machine):
  - Reboot / shutdown (with confirmation).
  - List installed systemd services and Docker containers, with search; start / stop / restart them.

# Installation Guide:
Paste the below command to ssh:
------------------------------------
curl -sSL https://raw.githubusercontent.com/khoidanghuy-cloud/nuc-monitor/main/install.sh | sudo bash
------------------------------------

The app is installed to `/opt/nuc-monitor` and runs as the systemd service `nuc-monitor`.

# Notes
- **Manage** logs in over SSH to `127.0.0.1:22`, so the SSH server must allow password login. The account needs sudo rights for reboot/shutdown and systemd service control.
- The Torrent tab needs aria2c running with RPC enabled. Download folder and subtitle-translate script paths are set at the top of `app.py` / in `translate_subtitle()`; edit them to match your machine.
- Traffic is plain HTTP: use it only on a trusted LAN, or put it behind HTTPS.
- After shutting down, keep the power off for at least 30 seconds before turning it on again, otherwise "After Power Failure = Power On" in the BIOS may not trigger.
