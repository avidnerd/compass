"""Build the web interface into the package at build time.

Why this exists: `uv tool install git+https://github.com/…/compass` should just
work. Installing from a git URL gets the source, not the built SPA, and Compass
serves its own interface — so without this the installed copy would start and
have nothing to show.

The hook builds `frontend/` into `backend/app/web/` when it is missing. It needs
npm, which anyone installing from git has a reasonable chance of having; a
prebuilt wheel (`make package`, or a GitHub release) needs nothing at all, and
the error below says so rather than failing cryptically.
"""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface

BACKEND = Path(__file__).resolve().parent
FRONTEND = BACKEND.parent / "frontend"
TARGET = BACKEND / "app" / "web"


class WebBuildHook(BuildHookInterface):
    PLUGIN_NAME = "compass-web"

    def initialize(self, version: str, build_data: dict) -> None:
        if (TARGET / "index.html").exists():
            return  # already built (make package, or a previous run)

        if not FRONTEND.is_dir():
            # Building from an sdist that carries app/web already; nothing to do.
            return

        npm = shutil.which("npm")
        if npm is None:
            raise RuntimeError(
                "Compass bundles a web interface that has to be built once, and npm was not "
                "found. Either install Node.js and retry, or install a prebuilt wheel from "
                "the project's releases instead of installing from source."
            )

        self.app.display_waiting("Building the Compass web interface (one time)…")
        install = "ci" if (FRONTEND / "package-lock.json").exists() else "install"
        subprocess.run([npm, install], cwd=FRONTEND, check=True)
        subprocess.run([npm, "run", "build"], cwd=FRONTEND, check=True)

        dist = FRONTEND / "dist"
        if not (dist / "index.html").exists():
            raise RuntimeError(f"npm run build produced no index.html in {dist}")
        shutil.rmtree(TARGET, ignore_errors=True)
        shutil.copytree(dist, TARGET)
