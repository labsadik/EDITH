use std::path::Path;
use std::process::Command;
use std::os::unix::process::CommandExt;
use std::thread;
use std::time::{Duration, Instant};
use crate::{add_if_exists, Options};

fn is_already_mounted(path: &Path) -> bool {
    let key = path.to_string_lossy();
    key == "/tmp" || ["/usr", "/bin", "/sbin", "/lib", "/lib64", "/etc/ssl/certs", "/etc/alternatives", "/dev", "/proc"]
        .iter().any(|base| key == *base || key.starts_with(&format!("{base}/")))
}

fn ensure_target_dirs(command: &mut Command, path: &Path) {
    let mut ancestors: Vec<_> = path.ancestors().filter(|item| *item != Path::new("/")).collect();
    ancestors.reverse();
    for item in ancestors {
        if !is_already_mounted(item) {
            command.arg("--dir").arg(item);
        }
    }
}

fn push_ro_bind(command: &mut Command, path: &Path) {
    let key = path.to_string_lossy();
    if is_already_mounted(path) { return; }
    if path.exists() {
        if let Some(parent) = path.parent() {
            ensure_target_dirs(command, parent);
        }
        command.arg("--ro-bind").arg(path).arg(&*key);
    }
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
    if let Some(parent) = options.workspace.parent() {
        ensure_target_dirs(&mut command, parent);
    }
    command.arg("--dir").arg(&workspace);
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
    let memory_bytes = options.memory_mb.saturating_mul(1024 * 1024);
    let cpu_seconds = options.cpu_seconds;
    unsafe {
        command.pre_exec(move || {
            let memory = libc::rlimit { rlim_cur: memory_bytes as libc::rlim_t, rlim_max: memory_bytes as libc::rlim_t };
            if libc::setrlimit(libc::RLIMIT_AS, &memory) != 0 {
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
