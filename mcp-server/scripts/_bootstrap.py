"""Shared bootstrap for MCP manual diagnostics."""

import os
import sys
from pathlib import Path


def prepare_project_imports() -> None:
    """Make the backend and MCP packages importable from this script directory."""
    mcp_root = Path(__file__).resolve().parents[1]
    project_root = mcp_root.parent
    backend_root = project_root / "backend"
    sys.path.insert(0, str(backend_root))
    sys.path.insert(0, str(mcp_root))
    os.chdir(backend_root)
