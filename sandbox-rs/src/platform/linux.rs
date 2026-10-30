use std::path::Path;
use std::process::Command;
use std::thread;
use std::time::{Duration, Instant};
use crate::{add_if_exists, Options};

fn push_ro_bind(command: &mut Command, path: &Path) {
    let key = path.to_string_lossy();
    if ["/usr", "/bin", "/sbin", "/lib", "/lib64", "/etc/ssl/certs", "/etc/alternatives"]
        .iter().any(|base| key == *base || key.starts_with(&format!("{base}/"))) { return; }
    add_if_exists(command, path, &key);
}

pub fn run(options: &Options) -> Result<i32, String> {
    if options.network {
        return Err(
            "Internet-enabled Linux sandbox runs are blocked until a restricted egress proxy/firewall backend is installed. No process was started.".into()
        );
    }
    let bwrap = std::env::var_os("EDITH_BWRAP").unwrap_or_else(|| "bwrap".into());
    let mut command = Command::new(bwrap);
    command.arg("--die-with-parent").arg("--new-session").arg("--unshare-all");
    for (source, target) in [
        ("/usr", "/usr"), ("/bin", "/bin"), ("/sbin", "/sbin"),
        ("/lib", "/lib"), ("/lib64", "/lib64"),
        ("/etc/alternatives", "/etc/alternatives"),
        ("/etc/ssl/certs", "/etc/ssl/certs"),
        ("/etc/ld.so.cache", "/etc/ld.so.cache"),
        ("/etc/resolv.conf", "/etc/resolv.conf"), ("/etc/hosts", "/etc/hosts"),
    ] { add_if_exists(&mut command, Path::new(source), target); }
    command.arg("--dev").arg("/dev").arg("--proc").arg("/proc").arg("--tmpfs").arg("/tmp");
    let workspace = options.workspace.to_string_lossy().to_string();
    command.arg("--bind").arg(&workspace).arg(&workspace).arg("--chdir").arg(&workspace);
    for path in &options.read_only { push_ro_bind(&mut command, path); }
    command.arg("--clearenv")
        .arg("--setenv").arg("HOME").arg(&workspace)
        .arg("--setenv").arg("TMPDIR").arg("/tmp")
        .arg("--setenv").arg("PYTHONDONTWRITEBYTECODE").arg("1")
        .arg("--setenv").arg("PYTHONUNBUFFERED").arg("1")
        .arg("--setenv").arg("LANG").arg("C.UTF-8");
    let mut path_dirs: Vec<String> = options.path_dirs.iter().map(|p| p.to_string_lossy().to_string()).collect();
    path_dirs.extend(["/usr/local/sbin", "/usr/local/bin", "/usr/sbin", "/usr/bin", "/sbin", "/bin"].iter().map(|s| s.to_string()));
    command.arg("--setenv").arg("PATH").arg(path_dirs.join(":"));
    command.arg("--").arg(&options.program).args(&options.args);
    let mut child = command.spawn().map_err(|e| format!("Could not start bubblewrap. Install bubblewrap and enable unprivileged user namespaces: {e}"))?;
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
