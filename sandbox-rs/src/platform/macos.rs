use std::fs;
use std::process::Command;
use std::thread;
use std::time::{Duration, Instant};
use crate::Options;

fn profile_path(path: &str) -> String { path.replace('\\\\', "\\\\\\\\").replace('"', "\\\\\\\"") }

pub fn run(options: &Options) -> Result<i32, String> {
    let workspace = options.workspace.to_string_lossy().to_string();
    let mut rules = vec![
        "(version 1)".to_string(),
        "(deny default)".to_string(),
        "(allow process*)".to_string(),
        "(allow sysctl-read)".to_string(),
        "(allow mach-lookup)".to_string(),
        "(allow file-read* (subpath \"/System\") (subpath \"/usr\") (subpath \"/Library\") (subpath \"/bin\") (subpath \"/sbin\"))".to_string(),
        format!("(allow file-read* (subpath \"{}\"))", profile_path(&workspace)),
        format!("(allow file-write* (subpath \"{}\"))", profile_path(&workspace)),
    ];
    for path in &options.read_only {
        rules.push(format!("(allow file-read* (subpath \"{}\"))", profile_path(&path.to_string_lossy())));
    }
    if options.network { rules.push("(allow network-outbound)".to_string()); }
    let profile = options.workspace.join(".edith-sandbox.sb");
    fs::write(&profile, rules.join("\\n")).map_err(|e| format!("Could not write sandbox profile: {e}"))?;
    let mut command = Command::new("sandbox-exec");
    command.arg("-f").arg(&profile).arg("--").arg(&options.program).args(&options.args);
    let mut child = command.spawn().map_err(|e| format!("macOS sandbox-exec unavailable; nothing was executed: {e}"))?;
    let started = Instant::now();
    loop {
        if let Some(status) = child.try_wait().map_err(|e| format!("Sandbox wait failed: {e}"))? {
            return Ok(status.code().unwrap_or(1));
        }
        if started.elapsed() >= Duration::from_secs(options.timeout) {
            let _ = child.kill();
            let _ = child.wait();
            return Ok(124);
        }
        thread::sleep(Duration::from_millis(40));
    }
}
