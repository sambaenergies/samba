mod samba_process;

use std::sync::Mutex;

use samba_process::SambaProcess;
use tauri::{AppHandle, Emitter, Manager, State};

struct SambaState {
    process: Mutex<Option<SambaProcess>>,
    backend_url: Mutex<Option<String>>,
}

#[tauri::command]
fn get_backend_url(state: State<SambaState>) -> Option<String> {
    state.backend_url.lock().ok()?.clone()
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

fn start_samba(app: &AppHandle, state: State<SambaState>) {
    if let Ok(process) = SambaProcess::start() {
        let backend_url = process.backend_url();
        if let Ok(mut backend_lock) = state.backend_url.lock() {
            *backend_lock = Some(backend_url.clone());
        }
        if let Ok(mut process_lock) = state.process.lock() {
            *process_lock = Some(process);
        }
        let _ = app.emit("samba-ready", backend_url);
    }
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .manage(SambaState {
            process: Mutex::new(None),
            backend_url: Mutex::new(None),
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
        .invoke_handler(tauri::generate_handler![get_backend_url, samba_shutdown])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
