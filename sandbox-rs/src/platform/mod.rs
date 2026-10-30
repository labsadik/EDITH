#[cfg(windows)]
mod windows;
#[cfg(target_os = "linux")]
mod linux;
#[cfg(target_os = "macos")]
mod macos;

use crate::Options;

#[cfg(windows)]
pub fn run(options: &Options) -> Result<i32, String> { windows::run(options) }
#[cfg(target_os = "linux")]
pub fn run(options: &Options) -> Result<i32, String> { linux::run(options) }
#[cfg(target_os = "macos")]
pub fn run(options: &Options) -> Result<i32, String> { macos::run(options) }
#[cfg(not(any(windows, target_os = "linux", target_os = "macos")))]
pub fn run(_options: &Options) -> Result<i32, String> { Err("This operating system has no enforced EDITH sandbox backend. Nothing was executed.".into()) }
