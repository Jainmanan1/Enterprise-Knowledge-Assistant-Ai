"""Shared bootstrap for backend manual diagnostics."""

def prepare_backend() -> None:
    import os
    import sys
    from pathlib import Path

    backend_root = Path(__file__).resolve().parents[1]
    backend_path = str(backend_root)

    if backend_path not in sys.path:
        sys.path.insert(0, backend_path)

    os.chdir(backend_root)
