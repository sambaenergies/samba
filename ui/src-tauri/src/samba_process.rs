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
    // Kept for its lifetime: on Windows it holds the Job Object handle whose
    // closure (on app exit, incl. crash) kills the backend. Unit elsewhere.
    _death_guard: DeathGuard,
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

        let mut cmd = Command::new(&exe);
        cmd.env("SAMBA_HOST", "127.0.0.1")
            .env("SAMBA_PORT", port.to_string())
            .env("SAMBA_SOLVER", "appsi_highs")
            // The webview's Origin differs by build/platform: the Vite dev server
            // (devUrl) in dev, and Tauri's custom protocol in a bundled app --
            // http on Linux/Windows, the tauri:// scheme on macOS. Allow exactly
            // those, not "*". (CORS is browser-enforced and is not an access
            // control -- any local process can still reach the loopback port; a
            // per-launch SAMBA_API_KEY would be the real guard. Tracked for #65.)
            .env(
                "SAMBA_CORS_ORIGINS",
                "http://localhost:1420,http://tauri.localhost,tauri://localhost",
            )
            .env("SAMBA_RUN_DIR", &run_dir)
            .env("SAMBA_DATA_DIR", &data_dir)
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null());

        // Linux: ask the kernel to SIGTERM the child if this process dies.
        set_parent_death_signal(&mut cmd);

        let child = cmd
            .spawn()
            .map_err(|err| format!("failed to spawn samba-server ({exe:?}): {err}"))?;

        // Windows: bind the child to a Job Object that the OS tears down (killing
        // the child) when this process exits. The guard is unit on other targets.
        #[allow(clippy::let_unit_value)]
        let death_guard = arm_death_guard(&child);

        let process = Self {
            port,
            child,
            _death_guard: death_guard,
        };
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
    /// Safety net for clean-exit paths that don't fire the window `Destroyed`
    /// event. A hard crash / SIGKILL of the app skips Drop entirely; that case is
    /// covered by the OS-level death signals armed at spawn (see
    /// `set_parent_death_signal` / `arm_death_guard`).
    fn drop(&mut self) {
        self.stop();
    }
}

// --- Parent-death cleanup ---------------------------------------------------
//
// The graceful path (Destroyed event, then Drop) handles a normal quit. These
// arm OS-level fallbacks so a *crash* of the app also takes the backend down.

/// On Linux, the spawned child is configured (pre-exec) to receive SIGTERM when
/// its parent dies. macOS has no clean equivalent and relies on the graceful
/// cleanup above.
///
/// PR_SET_PDEATHSIG triggers on the death of the parent *thread*, so this is only
/// correct while `start()` runs on a long-lived thread. It does today: it is
/// called from `setup()` (the Tauri main thread). Don't move the spawn onto a
/// short-lived worker (e.g. `thread::spawn`) or the backend would be killed when
/// that worker exits.
#[cfg(target_os = "linux")]
fn set_parent_death_signal(cmd: &mut Command) {
    use std::os::unix::process::CommandExt;
    // SAFETY: the closure runs in the forked child before exec and only calls
    // prctl(2), which is async-signal-safe.
    unsafe {
        cmd.pre_exec(|| {
            if libc::prctl(libc::PR_SET_PDEATHSIG, libc::SIGTERM) == -1 {
                return Err(std::io::Error::last_os_error());
            }
            Ok(())
        });
    }
}

#[cfg(not(target_os = "linux"))]
fn set_parent_death_signal(_cmd: &mut Command) {}

#[cfg(windows)]
type DeathGuard = Option<windows_job::JobGuard>;
#[cfg(not(windows))]
type DeathGuard = ();

/// On Windows, assign the child to a Job Object with KILL_ON_JOB_CLOSE so the OS
/// kills it when this process (and thus its job handle) goes away. Returns a
/// guard that owns the job handle for the backend's lifetime.
#[cfg(windows)]
fn arm_death_guard(child: &Child) -> DeathGuard {
    windows_job::arm(child)
}

#[cfg(not(windows))]
fn arm_death_guard(_child: &Child) -> DeathGuard {}

#[cfg(windows)]
mod windows_job {
    use std::os::windows::io::AsRawHandle;
    use std::process::Child;

    use windows_sys::Win32::Foundation::{CloseHandle, HANDLE};
    use windows_sys::Win32::System::JobObjects::{
        AssignProcessToJobObject, CreateJobObjectW, JobObjectExtendedLimitInformation,
        SetInformationJobObject, JOBOBJECT_EXTENDED_LIMIT_INFORMATION,
        JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE,
    };

    /// Owns a Job Object handle. Dropping (or the process exiting) closes the
    /// handle, which triggers KILL_ON_JOB_CLOSE on the assigned child.
    pub struct JobGuard(HANDLE);

    // The handle is only ever closed in Drop; safe to move across threads.
    unsafe impl Send for JobGuard {}

    impl Drop for JobGuard {
        fn drop(&mut self) {
            unsafe {
                CloseHandle(self.0);
            }
        }
    }

    pub fn arm(child: &Child) -> Option<JobGuard> {
        unsafe {
            let job = CreateJobObjectW(std::ptr::null(), std::ptr::null());
            if job.is_null() {
                return None;
            }
            let mut info: JOBOBJECT_EXTENDED_LIMIT_INFORMATION = std::mem::zeroed();
            info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE;
            let set = SetInformationJobObject(
                job,
                JobObjectExtendedLimitInformation,
                &info as *const _ as *const _,
                std::mem::size_of::<JOBOBJECT_EXTENDED_LIMIT_INFORMATION>() as u32,
            );
            if set == 0 {
                CloseHandle(job);
                return None;
            }
            if AssignProcessToJobObject(job, child.as_raw_handle() as HANDLE) == 0 {
                CloseHandle(job);
                return None;
            }
            Some(JobGuard(job))
        }
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
