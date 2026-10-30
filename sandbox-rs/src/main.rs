use std::env;
use std::path::PathBuf;
#[cfg(not(windows))]
use std::path::Path;
use std::process::ExitCode;

mod platform;

#[derive(Debug)]
struct Options {
    workspace: PathBuf,
    timeout: u64,
    memory_mb: u64,
    cpu_seconds: u64,
    network: bool,
    read_only: Vec<PathBuf>,
    path_dirs: Vec<PathBuf>,
    program: PathBuf,
    args: Vec<String>,
}

fn usage() -> &'static str {
    "Usage: edith-sandbox run --workspace DIR [--timeout SECONDS] [--memory-mb MB] [--cpu-seconds SECONDS] [--network deny|allow] [--read-only PATH]... [--path-dir PATH]... -- PROGRAM [ARG...]\nThe default policy is no network access, bounded CPU/memory, and write access only to the workspace."
}

fn parse_args() -> Result<Options, String> {
    let mut args = env::args().skip(1);
    let command = args.next().ok_or_else(|| usage().to_string())?;
    if command == "--version" || command == "version" {
        println!("edith-sandbox {}", env!("CARGO_PKG_VERSION"));
        std::process::exit(0);
    }
    if command != "run" { return Err(usage().to_string()); }
    let mut workspace = None;
    let mut timeout = 60u64;
    let mut memory_mb = 2048u64;
    let mut cpu_seconds: Option<u64> = None;
    let mut network = false;
    let mut read_only = Vec::new();
    let mut path_dirs = Vec::new();
    let mut command_vec: Vec<String> = Vec::new();
    let mut passthrough = false;
    while let Some(arg) = args.next() {
        if passthrough { command_vec.push(arg); continue; }
        match arg.as_str() {
            "--" => passthrough = true,
            "--workspace" => workspace = Some(PathBuf::from(args.next().ok_or("--workspace requires a path")?)),
            "--timeout" => timeout = args.next().ok_or("--timeout requires seconds")?.parse::<u64>().map_err(|_| "Invalid timeout")?.clamp(1, 3600),
            "--memory-mb" => memory_mb = args.next().ok_or("--memory-mb requires megabytes")?.parse::<u64>().map_err(|_| "Invalid memory limit")?.clamp(64, 8192),
            "--cpu-seconds" => cpu_seconds = Some(args.next().ok_or("--cpu-seconds requires seconds")?.parse::<u64>().map_err(|_| "Invalid CPU limit")?.clamp(1, 3600)),
            "--network" => network = match args.next().as_deref() { Some("deny") => false, Some("allow") => true, _ => return Err("--network must be deny or allow".into()) },
            "--read-only" => read_only.push(PathBuf::from(args.next().ok_or("--read-only requires a path")?)),
            "--path-dir" => path_dirs.push(PathBuf::from(args.next().ok_or("--path-dir requires a path")?)),
            _ => return Err(format!("Unknown option: {arg}\n{}", usage())),
        }
    }
    if !passthrough || command_vec.is_empty() { return Err(usage().to_string()); }
    let workspace = workspace.ok_or("--workspace is required")?;
    let workspace = workspace.canonicalize().map_err(|e| format!("Invalid workspace: {e}"))?;
    if !workspace.is_dir() { return Err("Workspace must be a directory".into()); }
    #[cfg(windows)]
    let is_root = workspace.parent().is_none();
    #[cfg(not(windows))]
    let is_root = workspace == Path::new("/") || workspace.parent().is_none();
    if is_root { return Err("A filesystem root cannot be used as an agent workspace".into()); }
    let program = PathBuf::from(command_vec.remove(0));
    let mut validated = Vec::new();
    for path in read_only {
        let canonical = path.canonicalize().map_err(|e| format!("Read-only path does not exist: {} ({e})", path.display()))?;
        if canonical.starts_with(&workspace) { continue; }
        validated.push(canonical);
    }
    let mut validated_path = Vec::new();
    for path in path_dirs {
        let canonical = path.canonicalize().map_err(|e| format!("PATH directory does not exist: {} ({e})", path.display()))?;
        if canonical.is_dir() { validated_path.push(canonical); }
    }
    Ok(Options {
        workspace, timeout, memory_mb, cpu_seconds: cpu_seconds.unwrap_or(timeout).clamp(1, 3600),
        network, read_only: validated, path_dirs: validated_path, program, args: command_vec,
    })
}

fn main() -> ExitCode {
    match parse_args() {
        Ok(options) => match platform::run(&options) {
            Ok(code) => ExitCode::from(code.clamp(0, 255) as u8),
            Err(error) => { eprintln!("EDITH_SANDBOX_ERROR: {error}"); ExitCode::from(125) }
        },
        Err(error) => { eprintln!("{error}"); ExitCode::from(125) }
    }
}

#[cfg(target_os = "linux")]
pub(crate) fn add_if_exists(command: &mut std::process::Command, source: &Path, destination: &str) {
    if source.exists() { command.arg("--ro-bind").arg(source).arg(destination); }
}
