#!/usr/bin/env python3
"""
Build script for MK3 Amplifier Network Diagnostic Tool.

This script packages the application as a standalone executable using PyInstaller.
Supports both Windows and macOS builds.

Usage:
    python build.py          # Build for current platform
    python build.py --clean  # Clean build artifacts first
"""

import subprocess
import sys
import shutil
import platform
from pathlib import Path

# Build configuration
APP_NAME = "MK3 Diagnostic Tool"
SCRIPT_PATH = "src/main.py"

# Read version from package
def get_version():
    """Read version from src/__init__.py."""
    init_path = Path("src/__init__.py")
    if init_path.exists():
        content = init_path.read_text()
        for line in content.splitlines():
            if line.startswith("__version__"):
                return line.split("=")[1].strip().strip('"\'')
    return "1.0.0"

VERSION = get_version()

# Platform detection
IS_WINDOWS = platform.system() == "Windows"
IS_MACOS = platform.system() == "Darwin"
IS_LINUX = platform.system() == "Linux"

# Platform-specific settings
if IS_WINDOWS:
    ICON_PATH = "public/sonancelogo.ico"
    DATA_SEPARATOR = ";"
elif IS_MACOS:
    # macOS uses .icns format, fall back to no icon if not available
    ICON_PATH = "public/sonancelogo.icns" if Path("public/sonancelogo.icns").exists() else None
    DATA_SEPARATOR = ":"
else:
    # Linux
    ICON_PATH = "public/sonancelogo.png" if Path("public/sonancelogo.png").exists() else None
    DATA_SEPARATOR = ":"


def get_pyinstaller_opts():
    """Get PyInstaller options for current platform."""
    opts = [
        "--name", APP_NAME.replace(" ", "_"),
        "--onefile",           # Single executable
        "--windowed",          # No console window (GUI app)
        "--clean",             # Clean build cache
        "--noconfirm",         # Overwrite without asking

        # Include public folder with logo (platform-specific separator)
        "--add-data", f"public{DATA_SEPARATOR}public",

        # Hidden imports that may be needed
        "--hidden-import", "dns.resolver",
        "--hidden-import", "dns.reversename",
        "--hidden-import", "zeroconf",
        "--hidden-import", "netifaces",
        "--hidden-import", "customtkinter",
        "--hidden-import", "PIL",

        # Collect all of customtkinter
        "--collect-all", "customtkinter",
    ]

    # macOS-specific options
    if IS_MACOS:
        opts.extend([
            "--osx-bundle-identifier", "com.sonance.mk3diagnostic",
        ])

    return opts


def clean():
    """Clean build artifacts."""
    dirs_to_clean = ["build", "dist", "__pycache__"]
    files_to_clean = list(Path(".").glob("*.spec"))

    for dir_name in dirs_to_clean:
        dir_path = Path(dir_name)
        if dir_path.exists():
            print(f"Removing {dir_path}...")
            shutil.rmtree(dir_path)

    for file_path in files_to_clean:
        print(f"Removing {file_path}...")
        file_path.unlink()

    # Clean __pycache__ in subdirectories
    for pycache in Path(".").rglob("__pycache__"):
        print(f"Removing {pycache}...")
        shutil.rmtree(pycache)


def build():
    """Build the executable."""
    platform_name = platform.system()
    print(f"Building {APP_NAME} v{VERSION} for {platform_name}...")
    print(f"Data separator: '{DATA_SEPARATOR}'")

    # Construct command - use sys.executable to ensure we use the same Python
    # that's running this script, avoiding PATH issues
    cmd = [sys.executable, "-m", "PyInstaller"] + get_pyinstaller_opts()

    if ICON_PATH and Path(ICON_PATH).exists():
        cmd.extend(["--icon", ICON_PATH])
        print(f"Using icon: {ICON_PATH}")
    else:
        print("No icon file found, building without icon")

    cmd.append(SCRIPT_PATH)

    print(f"\nRunning: {' '.join(cmd)}\n")

    # Run PyInstaller
    result = subprocess.run(cmd)

    if result.returncode == 0:
        print("\n" + "=" * 50)
        print("BUILD SUCCESSFUL!")
        print("=" * 50)

        # Find the output
        dist_path = Path("dist")
        if dist_path.exists():
            executables = list(dist_path.glob("*"))
            if executables:
                print(f"\nOutput location: {executables[0].absolute()}")

                if IS_MACOS:
                    print("\nmacOS Notes:")
                    print("  - The .app bundle can be found in dist/")
                    print("  - To distribute: zip the .app or create a DMG")
                    print("  - First launch may require: Right-click > Open")
                elif IS_WINDOWS:
                    print("\nWindows Notes:")
                    print("  - The .exe can be shared directly")
                    print("  - Windows Defender may flag unsigned executables")
    else:
        print("\n" + "=" * 50)
        print("BUILD FAILED!")
        print("=" * 50)
        sys.exit(1)


def main():
    """Main entry point."""
    print(f"Platform: {platform.system()} ({platform.machine()})")

    if "--clean" in sys.argv:
        clean()

    if "--clean-only" not in sys.argv:
        build()


if __name__ == "__main__":
    main()
