use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::thread;
use std::time::{Duration, Instant};

use tauri::{AppHandle, Manager};

pub struct SambaProcess {
    pub port: u16,
    child: Child,
}

impl SambaProcess {
    /// Start the bundled backend sidecar and block until it answers `/health`.
    pub fn start(app: &AppHandle) -> Result<Self, String> {
        let exe = resolve_server_binary(app)?;

        // Pick a free loopback port and hand it to the backend via SAMBA_PORT.
        // The frozen `samba-server` reads all config from SAMBA_* env vars (it is
        // not the Typer CLI, so there is no `--port` flag).
        let listener = TcpListener::bind("127.0.0.1:0").map_err(|err| err.to_string())?;
        let port = listener.local_addr().map_err(|err| err.to_string())?.port();
        drop(listener);

        // The backend must write run artifacts somewhere writable; the app's
        // local-data dir is the right home for a bundled desktop app.
        let data_dir = app
            .path()
            .app_local_data_dir()
            .map_err(|err| format!("no app data dir: {err}"))?;
        let run_dir = data_dir.join("runs");
        std::fs::create_dir_all(&run_dir).map_err(|err| err.to_string())?;

        let child = Command::new(&exe)
            .env("SAMBA_HOST", "127.0.0.1")
            .env("SAMBA_PORT", port.to_string())
            .env("SAMBA_SOLVER", "appsi_highs")
            // The webview's Origin differs by build/platform: the Vite dev server
            // (devUrl) in dev, and Tauri's custom protocol in a bundled app --
            // http on Linux/Windows, the tauri:// scheme on macOS. Allow exactly
            // those (not "*"): the backend is loopback-only, but an explicit list
            // keeps other local origins from reaching it.
            .env(
                "SAMBA_CORS_ORIGINS",
                "http://localhost:1420,http://tauri.localhost,tauri://localhost",
            )
            .env("SAMBA_RUN_DIR", &run_dir)
            .env("SAMBA_DATA_DIR", &data_dir)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|err| format!("failed to spawn samba-server ({exe:?}): {err}"))?;

        let process = Self { port, child };
        // The frozen binary cold-starts in ~1-2s; allow generous headroom for
        // slower machines.
        process.wait_until_ready(Duration::from_secs(30))?;
        Ok(process)
    }

    pub fn backend_url(&self) -> String {
        format!("http://127.0.0.1:{}", self.port)
    }

    fn wait_until_ready(&self, timeout: Duration) -> Result<(), String> {
        let deadline = Instant::now() + timeout;
        while Instant::now() < deadline {
            if is_health_ok(self.port) {
                return Ok(());
            }
            thread::sleep(Duration::from_millis(250));
        }
        Err("samba health check timeout".to_string())
    }

    pub fn stop(&mut self) {
        let _ = self.child.kill();
        let _ = self.child.wait();
    }
}

impl Drop for SambaProcess {
    /// Safety net: kill the backend whenever the handle is dropped, covering
    /// clean-exit paths that don't fire the window `Destroyed` event. (A hard
    /// crash / SIGKILL of the app still needs an OS-level death signal --
    /// tracked for the per-OS build matrix.)
    fn drop(&mut self) {
        self.stop();
    }
}

/// Locate the frozen `samba-server` binary.
///
/// In a bundled app it lives under the Tauri resource dir
/// (`binaries/samba-server/<exe>`, the PyInstaller onedir). For local dev/tests
/// the `SAMBA_SERVER_BIN` env var points directly at the binary so the app can
/// run without a full `tauri build`.
fn resolve_server_binary(app: &AppHandle) -> Result<PathBuf, String> {
    if let Ok(explicit) = std::env::var("SAMBA_SERVER_BIN") {
        let path = PathBuf::from(explicit);
        if path.is_file() {
            return Ok(path);
        }
        return Err(format!(
            "SAMBA_SERVER_BIN does not point at a file: {path:?}"
        ));
    }

    let exe_name = if cfg!(windows) {
        "samba-server.exe"
    } else {
        "samba-server"
    };
    let resource_dir = app
        .path()
        .resource_dir()
        .map_err(|err| format!("no resource dir: {err}"))?;
    let path = resource_dir
        .join("binaries")
        .join("samba-server")
        .join(exe_name);
    if path.is_file() {
        Ok(path)
    } else {
        Err(format!("bundled samba-server not found at {path:?}"))
    }
}

fn is_health_ok(port: u16) -> bool {
    let address = format!("127.0.0.1:{port}");
    let mut stream = match TcpStream::connect(address) {
        Ok(stream) => stream,
        Err(_) => return false,
    };

    let _ = stream.set_read_timeout(Some(Duration::from_millis(500)));
    let _ = stream.set_write_timeout(Some(Duration::from_millis(500)));

    if stream
        .write_all(b"GET /health HTTP/1.1\r\nHost: localhost\r\nConnection: close\r\n\r\n")
        .is_err()
    {
        return false;
    }

    let mut buffer = String::new();
    if stream.read_to_string(&mut buffer).is_err() {
        return false;
    }

    buffer.contains(" 200 ")
}
