# SAMBA Desktop App

The desktop app is a self-contained SAMBA you download and run — no Python
install, no command line. The window is a [Tauri](https://tauri.app) shell that
starts a **bundled SAMBA backend** on a local port and talks to it; everything
runs on your machine.

> **The builds are unsigned.** SAMBA does not yet pay for code-signing
> certificates, so macOS and Windows show a one-time "unidentified developer" /
> "unknown publisher" warning on first launch. The steps below include how to get
> past it. The app is open source — you can read or build it yourself from the
> repository.

## Download

Grab the installer for your platform from the
[Releases page](https://github.com/sambaenergies/samba/releases) (look for a
`ui-vX.Y.Z` release):

| Platform | File |
|---|---|
| **Linux** (Debian/Ubuntu) | `SAMBA_X.Y.Z_amd64.deb` |
| **Linux** (Fedora/RHEL/openSUSE) | `SAMBA-X.Y.Z-1.x86_64.rpm` |
| **Windows** (x64) | `SAMBA_X.Y.Z_x64-setup.exe` (or the `.msi`) |
| **macOS** (Apple Silicon) | `SAMBA_X.Y.Z_aarch64.dmg` |
| **macOS** (Intel) | `SAMBA_X.Y.Z_x64.dmg` |

> **macOS:** pick the `.dmg` for your chip — `aarch64` for Apple Silicon
> (M1/M2/M3…), `x64` for Intel.

## Install & first launch

### Linux

```bash
# Debian / Ubuntu
sudo apt install ./SAMBA_*_amd64.deb

# Fedora / RHEL
sudo dnf install ./SAMBA-*.x86_64.rpm
```

Then launch **SAMBA** from your application menu (or run `SAMBA`). The bundled
backend starts automatically; the window shows a brief "connecting" state on
first launch while it comes up.

### Windows

1. Run `SAMBA_X.Y.Z_x64-setup.exe` (or the `.msi`).
2. Windows **SmartScreen** may say *"Windows protected your PC."* Click
   **More info → Run anyway** (the app is unsigned, not unsafe).
3. Finish the installer and launch **SAMBA** from the Start menu.

### macOS

1. Open the `.dmg` and drag **SAMBA** to **Applications**.
2. The first time you open it, macOS **Gatekeeper** says the app *"cannot be
   opened because the developer cannot be verified."* Get past it one of two ways:
   - **Right-click** (or Control-click) the app in Applications → **Open** →
     **Open** in the dialog. macOS remembers the choice after the first time.
   - Or, from a terminal, clear the quarantine flag:
     ```bash
     xattr -dr com.apple.quarantine /Applications/SAMBA.app
     ```

## How it works (and what to expect)

- On launch the app starts the bundled backend on a random `127.0.0.1` port and
  waits for it to be ready before showing the UI.
- The backend is killed when you quit the app (and if the app crashes).
- The solver is **HiGHS**, bundled in-process — no separate solver install.
- Run artifacts are written under your OS's app-data directory for SAMBA.

## Troubleshooting

- **The window stays on "connecting" / "backend unreachable":** the bundled
  backend failed to start. This is most likely on a locked-down system; try
  launching from a terminal to see the error, or
  [open an issue](https://github.com/sambaenergies/samba/issues).
- **Antivirus quarantines the app:** unsigned bundles are sometimes flagged
  heuristically. Allow-list the app, or build from source.

## Prefer the command line or Python?

The desktop app is optional. You can also `pip install samba-core[cli]` and use
the [CLI](cli-reference.md), or run the [REST service](deployment.md) directly.
