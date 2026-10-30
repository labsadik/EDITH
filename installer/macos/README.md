# macOS package

The build workflow creates a component package for `/Applications`, then wraps it in a
Distribution package containing the same proprietary `LICENSE` used by the Windows
installer. The Installer UI offers the current user's home domain or local-system
installation domain. Packages are unsigned in CI; distribution outside a test environment
requires the publisher's Developer ID Installer certificate and notarization.
