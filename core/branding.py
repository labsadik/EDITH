"""EDITH's on-disk product naming and conservative upload-folder migration.

Never overwrite an existing user file. Legacy names occur only as migration
inputs; all paths newly created by EDITH use the EDITH product name.
"""
from __future__ import annotations

from pathlib import Path

UPLOAD_FOLDER_NAME = "EDITH Uploads"
_LEGACY_UPLOAD_FOLDER_NAME = "JARVIS Uploads"


def _collision_free_path(target: Path) -> Path:
    """Find an unused destination; never overwrite a pre-existing upload."""
    if not target.exists():
        return target
    for number in range(1, 10001):
        candidate = target.with_name(f"{target.stem}_migrated_{number}{target.suffix}")
        if not candidate.exists():
            return candidate
    raise OSError(f"No safe free name for {target.name}")


def migrate_named_directory(parent: Path, old_name: str, new_name: str) -> Path:
    """Migrate EDITH-owned legacy content while avoiding overwrites and symlinks."""
    target = parent / new_name
    legacy = parent / old_name
    if legacy.is_dir() and not legacy.is_symlink():
        if not target.exists() and not any(p.is_symlink() for p in legacy.iterdir()):
            legacy.rename(target)
        else:
            target.mkdir(parents=True, exist_ok=True)
            if target.is_symlink() or not target.is_dir():
                raise OSError("Target is not a regular directory")
            for entry in legacy.iterdir():
                if entry.is_symlink():
                    continue
                entry.rename(_collision_free_path(target / entry.name))
            try:
                legacy.rmdir()
            except OSError:
                pass
    target.mkdir(parents=True, exist_ok=True)
    return target


def migrate_legacy_uploads(parent: Path) -> Path:
    """Move old uploads into EDITH Uploads without overwriting user files."""
    return migrate_named_directory(
        parent, _LEGACY_UPLOAD_FOLDER_NAME, UPLOAD_FOLDER_NAME
    )


def prepare_agent_profiles_dir(home: Path | None = None) -> Path:
    """Keep existing browser sign-ins while switching to EDITH profile names."""
    home = home or Path.home()
    try:
        return migrate_named_directory(home, ".jarvis_profiles", ".edith_profiles")
    except OSError as exc:
        legacy = home / ".jarvis_profiles"
        if legacy.is_dir():
            # A browser may have locked its current profile. Do not lose sign-ins
            # or break browser automation merely to force a directory rename.
            print(f"[EDITH] Browser profile migration deferred: {type(exc).__name__}")
            return legacy
        raise


def prepare_projects_dir(home: Path | None = None) -> Path:
    """Retain generated projects when upgrading to the EDITH product name."""
    home = home or Path.home()
    desktop = home / "Desktop"
    desktop.mkdir(parents=True, exist_ok=True)
    return migrate_named_directory(desktop, "JarvisProjects", "EDITH Projects")


def prepare_uploads_dir(home: Path | None = None, base_dir: Path | None = None) -> Path:
    """Make EDITH's upload directory only when the dashboard is started."""
    home = home or Path.home()
    base_dir = base_dir or Path(__file__).resolve().parent.parent
    for parent in (home / "Downloads", home / "Documents"):
        if not parent.is_dir():
            continue
        try:
            return migrate_legacy_uploads(parent)
        except OSError as exc:
            print(f"[EDITH] Upload directory unavailable at {parent}: {type(exc).__name__}")
    fallback = base_dir / "uploads"  # Existing neutral fallback remains compatible
    fallback.mkdir(parents=True, exist_ok=True)
    return fallback
