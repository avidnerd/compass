"""Entry point for the PyInstaller build.

A frozen binary has no installed package to import `app.main:app` from by name,
so the app object is passed to uvicorn directly. Everything else — the data
directory, the generated secret, the browser launch — is the same code the
`compass` console command uses.
"""
import multiprocessing
import sys

if __name__ == "__main__":
    # Windows re-executes the binary for each child process; without this a
    # frozen app can fork itself endlessly.
    multiprocessing.freeze_support()
    from app.cli import main
    sys.exit(main())
