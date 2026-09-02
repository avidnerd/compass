# PyInstaller spec — a single executable for people who do not have Python.
#
# Build with:  make binary        (or: pyinstaller backend/compass.spec)
#
# These builds are UNSIGNED. macOS Gatekeeper and Windows SmartScreen will warn
# on first run; the README says how to get past it. Signing needs paid developer
# accounts, so it is deliberately not attempted here rather than half-done.

from pathlib import Path

from PyInstaller.utils.hooks import collect_submodules

BACKEND = Path(SPECPATH).resolve()

datas = [
    # Compass serves its own interface and applies its own migrations, so both
    # have to travel inside the binary.
    (str(BACKEND / "app" / "web"), "app/web"),
    (str(BACKEND / "migrations"), "app/migrations"),
]

# uvicorn resolves its protocol/loop implementations by name at runtime, so
# PyInstaller cannot see them by following imports.
hiddenimports = [
    *collect_submodules("uvicorn"),
    "uvicorn.logging",
    "uvicorn.loops.auto",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan.on",
    "aiosqlite",
    "app.main",
]

a = Analysis(
    [str(BACKEND / "run_binary.py")],
    pathex=[str(BACKEND)],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=["pytest", "tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name="compass",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    # A console window is correct here: the binary is a server that prints its
    # URL and stays running, and the user needs to see how to stop it.
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
