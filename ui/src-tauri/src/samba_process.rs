use std::io::{Read, Write};
use std::net::{TcpListener, TcpStream};
use std::process::{Child, Command, Stdio};
use std::thread;
use std::time::{Duration, Instant};

pub struct SambaProcess {
    pub port: u16,
    child: Child,
}

impl SambaProcess {
    pub fn start() -> Result<Self, String> {
        let listener = TcpListener::bind("127.0.0.1:0").map_err(|err| err.to_string())?;
        let port = listener
            .local_addr()
            .map_err(|err| err.to_string())?
            .port();
        drop(listener);

        let child = Command::new("samba")
            .arg("serve")
            .arg("--port")
            .arg(port.to_string())
            .env("SAMBA_CORS_ORIGINS", "http://localhost")
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null())
            .spawn()
            .map_err(|err| format!("failed to spawn samba serve: {err}"))?;

        let process = Self { port, child };
        process.wait_until_ready(Duration::from_secs(15))?;
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
