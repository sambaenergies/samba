mod samba_process;

use std::sync::Mutex;

use samba_process::SambaProcess;
use tauri::{AppHandle, Manager, State};

struct SambaState {
    process: Mutex<Option<SambaProcess>>,
    backend_url: Mutex<Option<String>>,
    startup_error: Mutex<Option<String>>,
}

#[tauri::command]
fn get_backend_url(state: State<SambaState>) -> Option<String> {
    state.backend_url.lock().ok()?.clone()
}

#[tauri::command]
fn get_startup_error(state: State<SambaState>) -> Option<String> {
    state.startup_error.lock().ok()?.clone()
}

#[tauri::command]
fn samba_shutdown(state: State<SambaState>) {
    if let Ok(mut process_lock) = state.process.lock() {
        if let Some(process) = process_lock.as_mut() {
            process.stop();
        }
        *process_lock = None;
    }
}

// Startup runs synchronously in `setup()`, before the webview boots, so emitted
// events would be lost (Tauri does not replay them for late subscribers). The
// result is therefore stored in state and *pulled* by the frontend at boot via
// `get_backend_url` / `get_startup_error`.
fn start_samba(app: &AppHandle, state: State<SambaState>) {
    match SambaProcess::start(app) {
        Ok(process) => {
            let backend_url = process.backend_url();
            if let Ok(mut backend_lock) = state.backend_url.lock() {
                *backend_lock = Some(backend_url);
            }
            if let Ok(mut process_lock) = state.process.lock() {
                *process_lock = Some(process);
            }
        }
        Err(err) => {
            if let Ok(mut error_lock) = state.startup_error.lock() {
                *error_lock = Some(err);
            }
        }
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(SambaState {
            process: Mutex::new(None),
            backend_url: Mutex::new(None),
            startup_error: Mutex::new(None),
        })
        .setup(|app| {
            let app_handle = app.handle().clone();
            let state: State<SambaState> = app.state();
            start_samba(&app_handle, state);
            Ok(())
        })
        .on_window_event(|window, event| {
            if let tauri::WindowEvent::Destroyed = event {
                let state: State<SambaState> = window.state();
                samba_shutdown(state);
            }
        })
        .plugin(tauri_plugin_opener::init())
        .invoke_handler(tauri::generate_handler![
            get_backend_url,
            get_startup_error,
            samba_shutdown
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
