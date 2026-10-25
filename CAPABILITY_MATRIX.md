# Platform capability matrix

Targets: Windows 10/11, macOS 13+, Ubuntu 22.04+; compatible Linux distributions
can use the same adapters. This matrix describes implemented paths and explicit limits, not proof of
physical testing. Automated results and outstanding device checks are recorded in VERIFICATION.md.

| Feature | Windows | macOS | Linux | Fallback / prerequisite |
| --- | --- | --- | --- | --- |
| CPU total/per-core/frequency/load | psutil; load if available | psutil | psutil | Missing individual field is null/N/A |
| Hardware inventory | CIM display/GPU/USB probes | system_profiler display/USB probes | DRM, PCI and USB probes | CPU, RAM, storage, network, audio, battery and attached-hardware fields use one stable result shape; unavailable probes return empty/N/A |
| Display and audio device lists | CIM / PortAudio | system_profiler / PortAudio | DRM / PortAudio | Inventory is read-only; it never invents device names or control support |
| RAM/swap/disk/I/O/uptime/processes | psutil | psutil | psutil | AccessDenied/missing sensor does not crash collector |
| Network counters/throughput/interfaces | psutil | psutil | psutil | First throughput sample N/A; counters are not an Internet speed test |
| Battery | psutil | psutil | psutil | Desktop/no sensor: N/A |
| NVIDIA GPU utilization | pynvml → nvidia-smi/WMI | model inventory; no general Apple GPU utilization claim | pynvml → nvidia-smi → lspci/sysfs inventory | Inventory does not imply load percentage; N/A when absent |
| Temperature | LibreHardwareMonitor/WMI when exposed | psutil if exposed | psutil sensors/sysfs | N/A; no fabricated temperature |
| Shell streaming/cwd/timeout/exit code | PowerShell → cmd | zsh → bash | bash → sh | Missing shell returns structured error; owner-requested hands-free app path logs the action without a separate confirmation |
| Process list/kill | psutil | psutil | psutil | Kill sensitive; permissions may deny; never target EDITH itself |
| Files/new/read/list/trash/overwrite | pathlib/send2trash | pathlib/send2trash | pathlib/send2trash | Permission tiers; irreversible fallback is not automatic |
| App launch/installed inventory | Start Menu/PATH | .app bundles/open | desktop entries/PATH/gtk-launch | No matching launcher: error, never claim foreground success |
| Window list | Win32 | AppleScript System Events | wmctrl on X11 | Accessibility permission; Wayland unsupported unless compositor API exists |
| Clipboard | Qt/pyperclip | Qt/pyperclip | Qt/pyperclip with session | Headless/Wayland/backend denial: unavailable |
| Screenshot/multi-monitor | mss | mss + Screen Recording permission | mss on X11 | Wayland needs portal; return unavailable, not a black fake capture |
| Volume | pycaw | osascript | pactl/wpctl | Missing audio service: unsupported |
| Brightness | WMI supported displays | optional brightness utility | brightnessctl | External displays/no interface: N/A/unsupported; do not silently simulate dimming |
| Sleep/restart/shutdown | OS power/UAC | AppleScript OS authorization | logind/systemctl/polkit | No separate EDITH confirmation; native OS authorization may still appear or deny the action |
| OS theme | winreg AppsUseLightTheme | defaults AppleInterfaceStyle | GNOME gsettings → KDE kdeglobals | Unknown dark; worker polls every 2s |
| Secure API secrets | keyring Windows Credential Manager | keyring Keychain | keyring Secret Service/KWallet | Keychain preferred. If unavailable, existing compatibility code retains a clearly labelled legacy plaintext value pending migration; secure storage cannot be claimed in that state. |
| Desktop UI | PyQt6 native Qt | PyQt6 native Qt | PyQt6 native Qt | Shared dark/light glass palette, bundled looping video on a black stage, native window controls and local SVG icons. Remote dashboard HTML is separate; WebEngine/Tailwind is not used for this desktop. |
| Three.js sphere / GSAP | Not implemented | Not implemented | Not implemented | The owner's later instruction keeps the existing exact bundled video and native Qt layout. No 60 fps claim. |
| Configured stdio MCP plugins | Supported | Supported | Supported | Gmail, GitHub and filesystem catalog entries are OFF by default and require an owner-supplied trusted MCP command. Disabled entries are unavailable to the model. Browser login can be opened only from that entry's configured URL; OAuth capability and tools depend on the selected server. |
| Microphone/speaker | PortAudio | PortAudio + mic permission | PortAudio/PipeWire/Pulse/ALSA | Text/remote input survive absent hardware; exact 16/24k formats checked |
| Camera | OpenCV | OpenCV + camera permission | OpenCV/V4L | Missing camera: explicit unavailable |
| Full arbitrary device/kernel/vehicle control | No | No | No | EDITH discovers and controls documented local OS capabilities. New hardware needs a matching OS API or a dedicated adapter; unknown hardware is reported, never simulated. |

Power/elevation, native desktop and live provider tests must be performed on real
supported targets. OS version support depends on installed Qt/PortAudio/browser
runtime and distribution libraries. Do not interpret mocked adapter selection as
Windows/macOS/Linux production certification.


