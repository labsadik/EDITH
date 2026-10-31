# macOS package and installation

## Supported target

The current desktop target is macOS 13 or later. The application uses the shared
PyQt6 desktop interface and macOS-specific adapters for device discovery, audio,
window access and generated-code isolation.

## Package format

The build workflow creates a component package for `/Applications`, then wraps it
in a Distribution package containing the same proprietary `LICENSE` used by the
Windows installer. The workflow can also create a DMG containing the PKG.

Packages produced by CI are unsigned. Distribution outside a test environment
requires the publisher's **Developer ID Installer** certificate and Apple
notarization. A repository clone or an unsigned test artifact should not be treated
as a notarized public release.

## First launch and permissions

1. Install the PKG using the macOS Installer.
2. Start EDITH from the installed application.
3. Grant microphone and camera permissions only when using those devices.
4. Grant **Screen Recording** permission for screenshot capture and **Accessibility**
   permission for supported window/desktop automation.
5. Check that the OS credential store is available before saving API credentials;
   EDITH reports when it must use its labelled local-config fallback.
6. Test Wi-Fi scanning and generated-project sandbox execution on the target Mac.
   These operations depend on the availability of the system scan utility and
   Seatbelt sandbox support.

The application does not bypass macOS privacy prompts or claim that a permission
was granted without the operating system making it available.
