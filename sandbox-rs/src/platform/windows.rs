#![allow(non_snake_case, dead_code)]
use std::collections::BTreeMap;
use std::ffi::c_void;
use std::hash::{Hash, Hasher};
use std::mem::{size_of, zeroed};
use std::os::windows::ffi::OsStrExt;
use std::path::{Path, PathBuf};
use std::ptr::{null, null_mut};
use std::time::Instant;
use crate::Options;

type Handle = *mut c_void;
type Sid = *mut c_void;
const SE_FILE_OBJECT: u32 = 1;
const DACL_SECURITY_INFORMATION: u32 = 0x00000004;
const SET_ACCESS: u32 = 2;
const TRUSTEE_IS_SID: u32 = 0;
const TRUSTEE_IS_UNKNOWN: u32 = 0;
const OBJECT_INHERIT_ACE: u32 = 0x1;
const CONTAINER_INHERIT_ACE: u32 = 0x2;
const FILE_TRAVERSE: u32 = 0x20;
const GENERIC_READ: u32 = 0x80000000;
const GENERIC_EXECUTE: u32 = 0x20000000;
const FILE_ALL_ACCESS: u32 = 0x001F01FF;
const PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES: usize = 0x00020009;
const EXTENDED_STARTUPINFO_PRESENT: u32 = 0x00080000;
const CREATE_SUSPENDED: u32 = 0x00000004;
const CREATE_UNICODE_ENVIRONMENT: u32 = 0x00000400;
const STARTF_USESTDHANDLES: u32 = 0x00000100;
const STD_INPUT_HANDLE: u32 = (-10i32) as u32;
const STD_OUTPUT_HANDLE: u32 = (-11i32) as u32;
const STD_ERROR_HANDLE: u32 = (-12i32) as u32;
const WAIT_OBJECT_0: u32 = 0;
const WAIT_TIMEOUT: u32 = 258;
const JOB_OBJECT_EXTENDED_LIMIT_INFORMATION: i32 = 9;
const JOB_OBJECT_LIMIT_PROCESS_TIME: u32 = 0x00000002;
const JOB_OBJECT_LIMIT_ACTIVE_PROCESS: u32 = 0x00000008;
const JOB_OBJECT_LIMIT_PROCESS_MEMORY: u32 = 0x00000100;
const JOB_OBJECT_LIMIT_JOB_MEMORY: u32 = 0x00000200;
const JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE: u32 = 0x00002000;

#[repr(C)] struct SidAndAttributes { Sid: Sid, Attributes: u32 }
#[repr(C)] struct SecurityCapabilities { AppContainerSid: Sid, Capabilities: *mut SidAndAttributes, CapabilityCount: u32, Reserved: u32 }
#[repr(C)] struct TrusteeW { pMultipleTrustee: *mut TrusteeW, MultipleTrusteeOperation: u32, TrusteeForm: u32, TrusteeType: u32, ptstrName: *mut u16 }
#[repr(C)] struct ExplicitAccessW { grfAccessPermissions: u32, grfAccessMode: u32, grfInheritance: u32, Trustee: TrusteeW }
#[repr(C)] struct StartupInfoW { cb: u32, lpReserved: *mut u16, lpDesktop: *mut u16, lpTitle: *mut u16, dwX: u32, dwY: u32, dwXSize: u32, dwYSize: u32, dwXCountChars: u32, dwYCountChars: u32, dwFillAttribute: u32, dwFlags: u32, wShowWindow: u16, cbReserved2: u16, lpReserved2: *mut u8, hStdInput: Handle, hStdOutput: Handle, hStdError: Handle }
#[repr(C)] struct StartupInfoExW { StartupInfo: StartupInfoW, lpAttributeList: *mut c_void }
#[repr(C)] struct ProcessInformation { hProcess: Handle, hThread: Handle, dwProcessId: u32, dwThreadId: u32 }
#[repr(C)] struct JobBasicLimitInformation { PerProcessUserTimeLimit: i64, PerJobUserTimeLimit: i64, LimitFlags: u32, MinimumWorkingSetSize: usize, MaximumWorkingSetSize: usize, ActiveProcessLimit: u32, Affinity: usize, PriorityClass: u32, SchedulingClass: u32 }
#[repr(C)] struct IoCounters { ReadOperationCount: u64, WriteOperationCount: u64, OtherOperationCount: u64, ReadTransferCount: u64, WriteTransferCount: u64, OtherTransferCount: u64 }
#[repr(C)] struct JobExtendedLimitInformation { BasicLimitInformation: JobBasicLimitInformation, IoInfo: IoCounters, ProcessMemoryLimit: usize, JobMemoryLimit: usize, PeakProcessMemoryUsed: usize, PeakJobMemoryUsed: usize }

#[link(name = "userenv")]
extern "system" {
    fn CreateAppContainerProfile(name: *const u16, display: *const u16, description: *const u16, capabilities: *const SidAndAttributes, count: u32, sid: *mut Sid) -> i32;
    fn DeriveAppContainerSidFromAppContainerName(name: *const u16, sid: *mut Sid) -> i32;
}
#[link(name = "advapi32")]
extern "system" {
    fn ConvertStringSidToSidW(string_sid: *const u16, sid: *mut Sid) -> i32;
    fn FreeSid(sid: Sid) -> Sid;
    fn GetNamedSecurityInfoW(name: *mut u16, object_type: u32, security_info: u32, owner: *mut Sid, group: *mut Sid, dacl: *mut *mut c_void, sacl: *mut *mut c_void, descriptor: *mut *mut c_void) -> u32;
    fn SetEntriesInAclW(count: u32, entries: *mut ExplicitAccessW, old_acl: *mut c_void, new_acl: *mut *mut c_void) -> u32;
    fn SetNamedSecurityInfoW(name: *mut u16, object_type: u32, security_info: u32, owner: Sid, group: Sid, dacl: *mut c_void, sacl: *mut c_void) -> u32;
}
#[link(name = "kernel32")]
extern "system" {
    fn LocalFree(memory: Handle) -> Handle;
    fn InitializeProcThreadAttributeList(list: *mut c_void, count: u32, flags: u32, size: *mut usize) -> i32;
    fn UpdateProcThreadAttribute(list: *mut c_void, flags: u32, attribute: usize, value: *mut c_void, size: usize, previous: *mut c_void, return_size: *mut usize) -> i32;
    fn DeleteProcThreadAttributeList(list: *mut c_void);
    fn CreateProcessW(application: *const u16, command_line: *mut u16, process_attributes: *mut c_void, thread_attributes: *mut c_void, inherit_handles: i32, creation_flags: u32, environment: *mut c_void, current_directory: *const u16, startup_info: *mut StartupInfoW, process_info: *mut ProcessInformation) -> i32;
    fn GetStdHandle(which: u32) -> Handle;
    fn CreateJobObjectW(attributes: *mut c_void, name: *const u16) -> Handle;
    fn SetInformationJobObject(job: Handle, class: i32, information: *mut c_void, length: u32) -> i32;
    fn AssignProcessToJobObject(job: Handle, process: Handle) -> i32;
    fn ResumeThread(thread: Handle) -> u32;
    fn WaitForSingleObject(handle: Handle, milliseconds: u32) -> u32;
    fn TerminateJobObject(job: Handle, exit_code: u32) -> i32;
    fn TerminateProcess(process: Handle, exit_code: u32) -> i32;
    fn GetExitCodeProcess(process: Handle, exit_code: *mut u32) -> i32;
    fn CloseHandle(handle: Handle) -> i32;
}

fn wide(value: &str) -> Vec<u16> { std::ffi::OsStr::new(value).encode_wide().chain(Some(0)).collect() }
fn check_win(ok: i32, label: &str) -> Result<(), String> { if ok == 0 { Err(format!("{label} failed with Windows error {}", std::io::Error::last_os_error())) } else { Ok(()) } }

fn debug_step(started: &Instant, label: &str) {
    if std::env::var_os("EDITH_SANDBOX_DEBUG").is_some() {
        eprintln!(
            "EDITH_SANDBOX_DEBUG {} elapsed_ms={}",
            label,
            started.elapsed().as_millis()
        );
    }
}

fn grant_acl(path: &Path, sid: Sid, permissions: u32, inheritance: u32) -> Result<(), String> {
    let mut name: Vec<u16> = path.as_os_str().encode_wide().chain(Some(0)).collect();
    let mut old_acl: *mut c_void = null_mut();
    let mut descriptor: *mut c_void = null_mut();
    let query = unsafe { GetNamedSecurityInfoW(name.as_mut_ptr(), SE_FILE_OBJECT, DACL_SECURITY_INFORMATION, null_mut(), null_mut(), &mut old_acl, null_mut(), &mut descriptor) };
    if query != 0 { return Err(format!("Cannot inspect ACL for {}: error {query}", path.display())); }
    let mut entry = ExplicitAccessW {
        grfAccessPermissions: permissions,
        grfAccessMode: SET_ACCESS,
        grfInheritance: inheritance,
        Trustee: TrusteeW { pMultipleTrustee: null_mut(), MultipleTrusteeOperation: 0, TrusteeForm: TRUSTEE_IS_SID, TrusteeType: TRUSTEE_IS_UNKNOWN, ptstrName: sid.cast() },
    };
    let mut new_acl: *mut c_void = null_mut();
    let update = unsafe { SetEntriesInAclW(1, &mut entry, old_acl, &mut new_acl) };
    unsafe { LocalFree(descriptor); }
    if update != 0 { return Err(format!("Cannot construct sandbox ACL for {}: error {update}", path.display())); }
    let set = unsafe { SetNamedSecurityInfoW(name.as_mut_ptr(), SE_FILE_OBJECT, DACL_SECURITY_INFORMATION, null_mut(), null_mut(), new_acl, null_mut()) };
    unsafe { LocalFree(new_acl); }
    if set != 0 { return Err(format!("Cannot apply sandbox ACL for {}: error {set}", path.display())); }
    Ok(())
}

fn grant_path(path: &Path, sid: Sid, writable: bool) -> Result<(), String> {
    // Change only the selected runtime directory/file. Windows normally grants
    // traverse checking to applications; never try to rewrite drive-root or
    // user-profile ancestor ACLs (which can require administrator privileges).
    let access = if writable { FILE_ALL_ACCESS } else { GENERIC_READ | GENERIC_EXECUTE };
    let inherit = if path.is_dir() { OBJECT_INHERIT_ACE | CONTAINER_INHERIT_ACE } else { 0 };
    grant_acl(path, sid, access, inherit)
}

fn grant_tree(root: &Path, sid: Sid, writable: bool) -> Result<(), String> {
    // An inheritable ACE on the workspace root applies to existing and new
    // child files/directories without recursively rewriting ACLs on thousands
    // of package files. Protected child DACLs remain inaccessible by design.
    let permissions = if writable { FILE_ALL_ACCESS } else { GENERIC_READ | GENERIC_EXECUTE };
    let inheritance = if root.is_dir() { OBJECT_INHERIT_ACE | CONTAINER_INHERIT_ACE } else { 0 };
    grant_acl(root, sid, permissions, inheritance)
}

fn normalize_windows_path(path: &Path) -> String {
    // canonicalize() commonly returns the Win32 extended-length prefix (\\?\).
    // Strip that prefix before comparing protected OS paths so System32 is
    // never mistaken for an ordinary runtime directory and modified by ACL.
    let mut value = path.to_string_lossy().replace('/', "\\").to_ascii_lowercase();
    if let Some(rest) = value.strip_prefix("\\\\?\\unc\\") {
        value = format!("\\\\{rest}");
    } else if let Some(rest) = value.strip_prefix("\\\\?\\") {
        value = rest.to_string();
    } else if let Some(rest) = value.strip_prefix("\\\\.\\") {
        value = rest.to_string();
    }
    value.trim_end_matches('\\').to_string()
}

fn is_windows_system_directory(path: &Path) -> bool {
    let root = std::env::var("SYSTEMROOT")
        .or_else(|_| std::env::var("WINDIR"))
        .unwrap_or_else(|_| r"C:\Windows".to_string());
    let system = PathBuf::from(root).join("System32");
    windows_path_is_within(path, &system)
}

fn windows_path_is_within(path: &Path, root: &Path) -> bool {
    let path = normalize_windows_path(path);
    let root = normalize_windows_path(root);
    path == root || path.strip_prefix(&root).is_some_and(|suffix| suffix.starts_with('\\'))
}

fn is_windows_program_files_path(path: &Path) -> bool {
    // Program Files may be installed on a non-system drive (for example,
    // D:\\Program Files\\Git). Environment variables only identify the
    // machine's default install root, so also recognize the conventional
    // root-level directory names on any drive. Match a complete first path
    // component to avoid treating similarly named folders as protected.
    let normalized = normalize_windows_path(path);
    let bytes = normalized.as_bytes();
    if bytes.len() < 3 || !bytes[0].is_ascii_alphabetic() || bytes[1] != b':' || bytes[2] != b'\\' {
        return false;
    }
    let first_component = normalized[3..].split('\\').next().unwrap_or_default();
    matches!(first_component, "program files" | "program files (x86)")
}

fn is_windows_default_readonly_path(path: &Path) -> bool {
    if is_windows_system_directory(path) || is_windows_program_files_path(path) {
        return true;
    }
    // Windows' standard Program Files ACLs already provide package read/execute
    // access. Avoid propagating a new inheritable ACE through huge SDK/runtime
    // trees (for example .NET), which is slow and unnecessary. These paths are
    // never granted write access by EDITH.
    ["ProgramFiles", "ProgramFiles(x86)"].iter().any(|name| {
        std::env::var(name)
            .ok()
            .is_some_and(|root| windows_path_is_within(path, Path::new(&root)))
    })
}

fn win32_path(path: &Path) -> PathBuf {
    // Keep filesystem/ACL operations on canonical paths, but pass ordinary
    // DOS/UNC paths to CreateProcess and child environment variables. cmd.exe
    // treats a \\?\ current directory as an unsupported UNC working directory.
    let value = path.to_string_lossy().replace('/', "\\");
    if let Some(rest) = value.strip_prefix("\\\\?\\UNC\\") {
        PathBuf::from(format!("\\\\{rest}"))
    } else if let Some(rest) = value.strip_prefix("\\\\?\\") {
        PathBuf::from(rest)
    } else if let Some(rest) = value.strip_prefix("\\\\.\\") {
        PathBuf::from(rest)
    } else {
        PathBuf::from(value)
    }
}

#[cfg(test)]
mod path_tests {
    use super::*;

    #[test]
    fn extended_length_system32_path_is_recognized() {
        let root = std::env::var("SYSTEMROOT")
            .or_else(|_| std::env::var("WINDIR"))
            .unwrap_or_else(|_| r"C:\Windows".to_string());
        let system = PathBuf::from(root).join("System32");
        let extended = PathBuf::from(format!("\\\\?\\{}", system.display()));

        assert!(is_windows_system_directory(&system));
        assert!(is_windows_system_directory(&extended));
    }

    #[test]
    fn system32_descendants_are_protected_from_acl_updates() {
        let root = std::env::var("SYSTEMROOT")
            .or_else(|_| std::env::var("WINDIR"))
            .unwrap_or_else(|_| r"C:\Windows".to_string());
        let powershell = PathBuf::from(root)
            .join("System32")
            .join("WindowsPowerShell")
            .join("v1.0");
        assert!(is_windows_system_directory(&powershell));
    }

    #[test]
    fn windows_path_comparison_ignores_case_and_trailing_separator() {
        let regular = Path::new(r"C:\Windows\System32\\");
        let differently_cased = Path::new(r"c:\WINDOWS\system32");
        assert_eq!(
            normalize_windows_path(regular),
            normalize_windows_path(differently_cased)
        );
    }

    #[test]
    fn program_files_subtrees_are_detected_without_prefix_collisions() {
        let root = Path::new(r"C:\Program Files");
        assert!(windows_path_is_within(
            Path::new(r"c:\program files\dotnet"),
            root
        ));
        assert!(windows_path_is_within(root, root));
        assert!(!windows_path_is_within(
            Path::new(r"C:\Program FilesBackup\tool"),
            root
        ));
    }

    #[test]
    fn program_files_on_nondefault_drives_are_protected_from_acl_updates() {
        assert!(is_windows_default_readonly_path(Path::new(
            r"D:\Program Files\Git\cmd"
        )));
        assert!(is_windows_default_readonly_path(Path::new(
            r"\\?\D:\Program Files (x86)\Tool\bin"
        )));
        assert!(!is_windows_default_readonly_path(Path::new(
            r"D:\Program FilesBackup\tool"
        )));
        assert!(!is_windows_default_readonly_path(Path::new(
            r"D:\Development\Program Files\tool"
        )));
    }

    #[test]
    fn process_path_strips_extended_length_prefix() {
        let extended = Path::new(r"\\?\D:\work\project");
        assert_eq!(win32_path(extended), PathBuf::from(r"D:\work\project"));
    }

    #[test]
    fn process_path_converts_extended_unc_prefix() {
        let extended = Path::new(r"\\?\UNC\server\share\project");
        assert_eq!(win32_path(extended), PathBuf::from(r"\\server\share\project"));
    }
}

fn appcontainer_sid(workspace: &Path) -> Result<Sid, String> {
    let mut hasher = std::collections::hash_map::DefaultHasher::new();
    workspace.to_string_lossy().to_lowercase().hash(&mut hasher);
    let name = wide(&format!("EDITH-AgentSandbox-{:016x}", hasher.finish()));
    let display = wide("EDITH Agent Sandbox");
    let description = wide("Non-admin, workspace-confined execution environment for EDITH agents");
    let mut sid: Sid = null_mut();
    let created = unsafe { CreateAppContainerProfile(name.as_ptr(), display.as_ptr(), description.as_ptr(), null(), 0, &mut sid) };
    if created >= 0 && !sid.is_null() { return Ok(sid); }
    let derived = unsafe { DeriveAppContainerSidFromAppContainerName(name.as_ptr(), &mut sid) };
    if derived != 0 || sid.is_null() { return Err(format!("Could not create or derive Windows AppContainer SID (HRESULT 0x{created:08x}, error {derived})")); }
    Ok(sid)
}

fn quote_arg(value: &str) -> String {
    if !value.is_empty() && !value.chars().any(|c| c.is_whitespace() || c == '"') { return value.to_string(); }
    let mut out = String::from("\"");
    let mut slashes = 0usize;
    for ch in value.chars() {
        if ch == '\\' { slashes += 1; continue; }
        if ch == '"' { out.push_str(&"\\".repeat(slashes * 2 + 1)); out.push('"'); slashes = 0; continue; }
        out.push_str(&"\\".repeat(slashes)); slashes = 0; out.push(ch);
    }
    out.push_str(&"\\".repeat(slashes * 2));
    out.push('"');
    out
}

fn safe_environment(options: &Options, temp: &Path) -> Vec<u16> {
    let workspace = win32_path(&options.workspace);
    let temp = win32_path(temp);
    let mut values: BTreeMap<String, String> = BTreeMap::new();
    for key in [
        "SYSTEMROOT", "WINDIR", "COMSPEC", "PATHEXT",
        "PROCESSOR_ARCHITECTURE", "NUMBER_OF_PROCESSORS",
        "PROGRAMFILES", "PROGRAMFILES(X86)",
    ] {
        if let Ok(value) = std::env::var(key) {
            values.insert(key.to_string(), value);
        }
    }
    let system_root = values
        .get("SYSTEMROOT")
        .or_else(|| values.get("WINDIR"))
        .cloned()
        .unwrap_or_else(|| r"C:\Windows".to_string());
    values.insert("SYSTEMROOT".into(), system_root.clone());
    values.insert("WINDIR".into(), system_root.clone());
    values.insert("COMSPEC".into(), format!(r"{system_root}\System32\cmd.exe"));
    let mut path_dirs = vec![PathBuf::from(format!(r"{system_root}\System32"))];
    path_dirs.extend(options.path_dirs.iter().map(|path| win32_path(path)));
    path_dirs.push(workspace.join(".venv/Scripts"));
    path_dirs.push(workspace.clone());
    values.insert(
        "PATH".into(),
        std::env::join_paths(path_dirs).unwrap_or_default().to_string_lossy().to_string(),
    );
    values.insert("USERPROFILE".into(), workspace.join(".edith-home").to_string_lossy().to_string());
    values.insert("HOMEDRIVE".into(), workspace.to_string_lossy().chars().take(2).collect());
    values.insert("HOMEPATH".into(), workspace.join(".edith-home").to_string_lossy().to_string());
    values.insert("TEMP".into(), temp.to_string_lossy().to_string());
    values.insert("TMP".into(), temp.to_string_lossy().to_string());
    values.insert("APPDATA".into(), workspace.join(".edith-appdata").to_string_lossy().to_string());
    values.insert("LOCALAPPDATA".into(), workspace.join(".edith-local").to_string_lossy().to_string());
    values.insert("PYTHONDONTWRITEBYTECODE".into(), "1".into());
    values.insert("PYTHONUNBUFFERED".into(), "1".into());
    values.insert("PYTHONNOUSERSITE".into(), "1".into());
    values.insert("EDITH_SANDBOX".into(), "1".into());
    let mut block = Vec::new();
    for (key, value) in values {
        block.extend(format!("{key}={value}").encode_utf16());
        block.push(0);
    }
    block.push(0);
    block
}

fn make_job(timeout: u64, memory_mb: u64) -> Result<Handle, String> {
    let job = unsafe { CreateJobObjectW(null_mut(), null()) };
    if job.is_null() { return Err(format!("CreateJobObjectW failed: {}", std::io::Error::last_os_error())); }
    let mut info: JobExtendedLimitInformation = unsafe { zeroed() };
    info.BasicLimitInformation.LimitFlags = JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE | JOB_OBJECT_LIMIT_ACTIVE_PROCESS | JOB_OBJECT_LIMIT_PROCESS_MEMORY | JOB_OBJECT_LIMIT_JOB_MEMORY | JOB_OBJECT_LIMIT_PROCESS_TIME;
    info.BasicLimitInformation.ActiveProcessLimit = 64;
    info.BasicLimitInformation.PerProcessUserTimeLimit = (timeout.min(3600) as i64) * 10_000_000;
    let memory_bytes = (memory_mb.clamp(64, 8192) * 1024 * 1024) as usize;
    info.ProcessMemoryLimit = memory_bytes;
    info.JobMemoryLimit = memory_bytes.saturating_mul(2);
    let ok = unsafe { SetInformationJobObject(job, JOB_OBJECT_EXTENDED_LIMIT_INFORMATION, (&mut info as *mut JobExtendedLimitInformation).cast(), size_of::<JobExtendedLimitInformation>() as u32) };
    if ok == 0 { unsafe { CloseHandle(job); } return Err(format!("Could not set sandbox resource limits: {}", std::io::Error::last_os_error())); }
    Ok(job)
}

pub fn run(options: &Options) -> Result<i32, String> {
    let started = Instant::now();
    debug_step(&started, "prepare workspace");
    let workspace = &options.workspace;
    let temp = workspace.join(".edith-tmp");
    for path in [&temp, &workspace.join(".edith-home"), &workspace.join(".edith-appdata"), &workspace.join(".edith-local")] {
        std::fs::create_dir_all(path).map_err(|e| format!("Cannot prepare sandbox directory {}: {e}", path.display()))?;
    }
    debug_step(&started, "create AppContainer profile");
    let sid = appcontainer_sid(workspace)?;
    debug_step(&started, "created AppContainer profile");
    let result = (|| {
        debug_step(&started, "grant workspace ACL");
        grant_tree(workspace, sid, true)?;
        debug_step(&started, "granted workspace ACL");
        for path in &options.read_only {
            if path.exists() && !path.starts_with(workspace) && !is_windows_default_readonly_path(path) {
                debug_step(&started, &format!("grant read-only ACL {}", path.display()));
                grant_tree(path, sid, false)?;
                debug_step(&started, &format!("granted read-only ACL {}", path.display()));
            }
        }
        let app = if options.program.is_absolute() { options.program.clone() } else {
            std::env::split_paths(&std::env::var_os("PATH").unwrap_or_default())
                .map(|dir| dir.join(&options.program)).find(|p| p.is_file())
                .ok_or_else(|| format!("Sandbox executable not found: {}", options.program.display()))?
        };
        let app = win32_path(&app);
        if !app.is_file() { return Err(format!("Sandbox executable does not exist: {}", app.display())); }
        if !app.starts_with(workspace) && !is_windows_default_readonly_path(app.parent().unwrap_or(Path::new(""))) {
            grant_path(app.parent().ok_or("Executable has no parent directory")?, sid, false)?;
            grant_acl(&app, sid, GENERIC_READ | GENERIC_EXECUTE, 0)?;
        }
        let mut capabilities = Vec::<SidAndAttributes>::new();
        let mut internet_sid: Sid = null_mut();
        if options.network {
            let internet = wide("S-1-15-3-1");
            check_win(unsafe { ConvertStringSidToSidW(internet.as_ptr(), &mut internet_sid) }, "ConvertStringSidToSidW(InternetClient)")?;
            capabilities.push(SidAndAttributes { Sid: internet_sid, Attributes: 0 });
        }
        let mut security = SecurityCapabilities {
            AppContainerSid: sid,
            Capabilities: if capabilities.is_empty() { null_mut() } else { capabilities.as_mut_ptr() },
            CapabilityCount: capabilities.len() as u32,
            Reserved: 0,
        };
        let mut attribute_size = 0usize;
        unsafe { InitializeProcThreadAttributeList(null_mut(), 1, 0, &mut attribute_size); }
        if attribute_size == 0 { if !internet_sid.is_null() { unsafe { LocalFree(internet_sid); } } return Err("Could not size AppContainer process attributes".into()); }
        let mut attribute_storage = vec![0u64; (attribute_size + 7) / 8];
        let attributes = attribute_storage.as_mut_ptr().cast::<c_void>();
        check_win(unsafe { InitializeProcThreadAttributeList(attributes, 1, 0, &mut attribute_size) }, "InitializeProcThreadAttributeList")?;
        let attribute_result = unsafe { UpdateProcThreadAttribute(attributes, 0, PROC_THREAD_ATTRIBUTE_SECURITY_CAPABILITIES, (&mut security as *mut SecurityCapabilities).cast(), size_of::<SecurityCapabilities>(), null_mut(), null_mut()) };
        if attribute_result == 0 {
            unsafe { DeleteProcThreadAttributeList(attributes); if !internet_sid.is_null() { LocalFree(internet_sid); } }
            return Err(format!("Could not apply AppContainer capability boundary: {}", std::io::Error::last_os_error()));
        }
        let command_line = std::iter::once(app.to_string_lossy().to_string()).chain(options.args.iter().cloned()).map(|arg| quote_arg(&arg)).collect::<Vec<_>>().join(" ");
        let app_wide: Vec<u16> = app.as_os_str().encode_wide().chain(Some(0)).collect();
        let mut command_wide: Vec<u16> = command_line.encode_utf16().chain(Some(0)).collect();
        let cwd_path = win32_path(workspace);
        let mut cwd: Vec<u16> = cwd_path.as_os_str().encode_wide().chain(Some(0)).collect();
        let mut env_block = safe_environment(options, &temp);
        let mut startup: StartupInfoExW = unsafe { zeroed() };
        startup.StartupInfo.cb = size_of::<StartupInfoExW>() as u32;
        startup.StartupInfo.dwFlags = STARTF_USESTDHANDLES;
        startup.StartupInfo.hStdInput = unsafe { GetStdHandle(STD_INPUT_HANDLE) };
        startup.StartupInfo.hStdOutput = unsafe { GetStdHandle(STD_OUTPUT_HANDLE) };
        startup.StartupInfo.hStdError = unsafe { GetStdHandle(STD_ERROR_HANDLE) };
        startup.lpAttributeList = attributes;
        let mut process: ProcessInformation = unsafe { zeroed() };
        debug_step(&started, "create AppContainer child process");
        let created = unsafe { CreateProcessW(app_wide.as_ptr(), command_wide.as_mut_ptr(), null_mut(), null_mut(), 1, EXTENDED_STARTUPINFO_PRESENT | CREATE_SUSPENDED | CREATE_UNICODE_ENVIRONMENT, env_block.as_mut_ptr().cast(), cwd.as_mut_ptr(), (&mut startup as *mut StartupInfoExW).cast(), &mut process) };
        debug_step(&started, "created AppContainer child process");
        unsafe { DeleteProcThreadAttributeList(attributes); if !internet_sid.is_null() { LocalFree(internet_sid); } }
        check_win(created, "CreateProcessW(AppContainer)")?;
        let job = match make_job(options.cpu_seconds, options.memory_mb) {
            Ok(value) => value,
            Err(error) => { unsafe { TerminateProcess(process.hProcess, 125); CloseHandle(process.hThread); CloseHandle(process.hProcess); } return Err(error); }
        };
        if unsafe { AssignProcessToJobObject(job, process.hProcess) } == 0 {
            let error = format!("Could not place child in the resource-limited Job Object: {}", std::io::Error::last_os_error());
            unsafe { TerminateProcess(process.hProcess, 125); CloseHandle(job); CloseHandle(process.hThread); CloseHandle(process.hProcess); }
            return Err(error);
        }
        if unsafe { ResumeThread(process.hThread) } == u32::MAX {
            let error = format!("Could not resume sandboxed process: {}", std::io::Error::last_os_error());
            unsafe { TerminateJobObject(job, 125); CloseHandle(job); CloseHandle(process.hThread); CloseHandle(process.hProcess); }
            return Err(error);
        }
        let wait_ms = (options.timeout.saturating_mul(1000)).min(u32::MAX as u64 - 1) as u32;
        debug_step(&started, "wait for AppContainer child");
        let wait = unsafe { WaitForSingleObject(process.hProcess, wait_ms) };
        debug_step(&started, "AppContainer child wait completed");
        let code = if wait == WAIT_TIMEOUT {
            unsafe { TerminateJobObject(job, 124); WaitForSingleObject(process.hProcess, 5000); }
            124
        } else if wait == WAIT_OBJECT_0 {
            let mut exit_code = 1u32;
            if unsafe { GetExitCodeProcess(process.hProcess, &mut exit_code) } == 0 { 1 } else { exit_code as i32 }
        } else {
            unsafe { TerminateJobObject(job, 125); }
            125
        };
        unsafe { CloseHandle(process.hThread); CloseHandle(process.hProcess); CloseHandle(job); }
        Ok(code)
    })();
    unsafe { FreeSid(sid); }
    result
}
