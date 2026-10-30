use std::fs;
use std::path::Path;
use std::process::Command;
use std::os::unix::process::CommandExt;
use std::thread;
use std::time::{Duration, Instant};
use crate::Options;

fn profile_path(path: &str) -> String {
    path.replace('\\', "\\\\").replace('"', "\\\"")
}

pub fn run(options: &Options) -> Result<i32, String> {
    if options.network {
        return Err(
            "Internet-enabled macOS sandbox runs are blocked until a restricted egress proxy/firewall backend is installed. No process was started.".into()
        );
    }
    let workspace = options.workspace.to_string_lossy().to_string();
    let home = options.workspace.join(".edith-home");
    let temp = options.workspace.join(".edith-tmp");
    fs::create_dir_all(&home).map_err(|e| format!("Cannot prepare sandbox home: {e}"))?;
    fs::create_dir_all(&temp).map_err(|e| format!("Cannot prepare sandbox temp: {e}"))?;

    let mut rules = vec![
        "(version 1)".to_string(),
        "(deny default)".to_string(),
        "(allow process*)".to_string(),
        "(allow sysctl-read)".to_string(),
        "(allow mach-lookup)".to_string(),
        "(allow file-read* (subpath \"/System\") (subpath \"/usr\") (subpath \"/Library\") (subpath \"/bin\") (subpath \"/sbin\"))".to_string(),
        format!("(allow file-read* (subpath \"{}\"))", profile_path(&workspace)),
        format!("(allow file-write* (subpath \"{}\"))", profile_path(&workspace)),
        format!("(allow file-read* (subpath \"{}\"))", profile_path(&home.to_string_lossy())),
        format!("(allow file-write* (subpath \"{}\"))", profile_path(&home.to_string_lossy())),
        format!("(allow file-read* (subpath \"{}\"))", profile_path(&temp.to_string_lossy())),
        format!("(allow file-write* (subpath \"{}\"))", profile_path(&temp.to_string_lossy())),
    ];
    for path in &options.read_only {
        let value = path.to_string_lossy();
        if Path::new(value.as_ref()).exists() {
            rules.push(format!("(allow file-read* (subpath \"{}\"))", profile_path(&value)));
        }
    }
    // Keep the policy outside the writable project tree, so sandboxed code
    // cannot loosen its own restrictions by editing the profile after launch.
    let profile = std::env::temp_dir().join(format!("edith-sandbox-{}.sb", std::process::id()));
    fs::write(&profile, rules.join("\n"))
        .map_err(|e| format!("Could not write sandbox profile: {e}"))?;

    let mut path_dirs: Vec<String> = options.path_dirs.iter()
        .map(|path| path.to_string_lossy().to_string()).collect();
    path_dirs.extend(["/usr/local/bin", "/opt/homebrew/bin", "/usr/bin", "/bin"]
        .iter().map(|item| item.to_string()));
    let mut command = Command::new("sandbox-exec");
    command.arg("-f").arg(&profile).arg("--").arg(&options.program)
        .args(&options.args).current_dir(&options.workspace)
        .env_clear()
        .env("PATH", path_dirs.join(":"))
        .env("HOME", &home)
        .env("TMPDIR", &temp)
        .env("PYTHONDONTWRITEBYTECODE", "1")
        .env("PYTHONUNBUFFERED", "1")
        .env("PYTHONNOUSERSITE", "1")
        .env("EDITH_SANDBOX", "1");

    let memory_bytes = options.memory_mb.saturating_mul(1024 * 1024);
    let cpu_seconds = options.cpu_seconds;
    unsafe {
        command.pre_exec(move || {
            // RLIMIT_DATA is portable across supported macOS releases.
            let memory = libc::rlimit { rlim_cur: memory_bytes as libc::rlim_t, rlim_max: memory_bytes as libc::rlim_t };
            if libc::setrlimit(libc::RLIMIT_DATA, &memory) != 0 {
                return Err(std::io::Error::last_os_error());
            }
            let cpu = libc::rlimit { rlim_cur: cpu_seconds as libc::rlim_t, rlim_max: cpu_seconds as libc::rlim_t };
            if libc::setrlimit(libc::RLIMIT_CPU, &cpu) != 0 {
                return Err(std::io::Error::last_os_error());
            }
            let file_size = libc::rlimit { rlim_cur: 1024 * 1024 * 1024, rlim_max: 1024 * 1024 * 1024 };
            if libc::setrlimit(libc::RLIMIT_FSIZE, &file_size) != 0 {
                return Err(std::io::Error::last_os_error());
            }
            Ok(())
        });
    }

    let mut child = match command.spawn() {
        Ok(value) => value,
        Err(error) => {
            let _ = fs::remove_file(&profile);
            return Err(format!("macOS sandbox-exec unavailable; nothing was executed: {error}"));
        }
    };
    let started = Instant::now();
    let result = loop {
        match child.try_wait() {
            Ok(Some(status)) => break Ok(status.code().unwrap_or(1)),
            Ok(None) => {}
            Err(error) => break Err(format!("Sandbox wait failed: {error}")),
        }
        if started.elapsed() >= Duration::from_secs(options.timeout) {
            let _ = child.kill();
            let _ = child.wait();
            break Ok(124);
        }
        thread::sleep(Duration::from_millis(40));
    };
    let _ = fs::remove_file(&profile);
    result
}
