#!/usr/bin/env python3
"""
Media Downloader Helper Script
==============================
Invoked by AI Agents to execute downloads from any directory.
"""

import sys
from pathlib import Path

# Resolve parent root directory of the tool
CURRENT_DIR = Path(__file__).parent.resolve()
TOOL_ROOT = CURRENT_DIR.parents[2]  # from .agents/skills/media-downloader/scripts to repo root

if not (TOOL_ROOT / "cli.py").exists():
    # If installed directly into an agent's global skills directory, check parent directories
    candidate = CURRENT_DIR
    while candidate.parent != candidate:
        if (candidate / "cli.py").exists():
            TOOL_ROOT = candidate
            break
        candidate = candidate.parent

sys.path.insert(0, str(TOOL_ROOT))

from cli import main

if __name__ == "__main__":
    main()
