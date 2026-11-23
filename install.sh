#!/usr/bin/env bash
# Media Downloader Skill Installer for Linux / macOS
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "🤖 Installing Media Downloader Agent Skill..."
python3 install.py "$@"
