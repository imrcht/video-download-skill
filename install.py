#!/usr/bin/env python3
"""
Media Downloader Skill Installer
================================
Installs the Media Downloader skill for AI Agents:
  - Antigravity / Gemini CLI
  - Claude Code
  - Cursor
  - OpenAI Codex / Generic Agents

Usage:
    python install.py                   # Interactive or auto-detect
    python install.py --all             # Install to all detected agent environments
    python install.py --agent claude    # Install to Claude Code
    python install.py --agent cursor    # Install to Cursor
    python install.py --agent antigravity # Install to Antigravity / Gemini
    python install.py --agent codex     # Install to Codex / .agents
"""

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).parent.resolve()
SKILL_SOURCE = REPO_ROOT / ".agents" / "skills" / "media-downloader"
SKILL_MD_SOURCE = REPO_ROOT / "SKILL.md"


def get_user_home() -> Path:
    """Return user home directory cross-platform."""
    return Path.home()


def install_antigravity(symlink: bool = False) -> bool:
    """Install skill to Antigravity global config (~/.gemini/config/skills/media-downloader)."""
    target = get_user_home() / ".gemini" / "config" / "skills" / "media-downloader"
    return copy_or_link_skill("Antigravity", target, symlink)


def install_claude(symlink: bool = False) -> bool:
    """Install skill to Claude Code (~/.claude/skills/media-downloader)."""
    target = get_user_home() / ".claude" / "skills" / "media-downloader"
    return copy_or_link_skill("Claude Code", target, symlink)


def install_cursor(symlink: bool = False) -> bool:
    """Install skill and rule to Cursor."""
    # 1. Skill folder
    target = REPO_ROOT / ".cursor" / "skills" / "media-downloader"
    success = copy_or_link_skill("Cursor", target, symlink)

    # 2. Also write Cursor Rule (.cursor/rules/media-downloader.mdc)
    rules_dir = REPO_ROOT / ".cursor" / "rules"
    rules_dir.mkdir(parents=True, exist_ok=True)
    rule_file = rules_dir / "media-downloader.mdc"

    cursor_rule_content = f"""---
description: Automatically download Instagram Reels and YouTube videos/shorts given a URL with video and audio references.
globs: *
alwaysApply: false
---

# Media Downloader Skill for Cursor

When analyzing Instagram reels or YouTube links provided by the user:
1. Run the downloader:
   ```bash
   python {REPO_ROOT / 'cli.py'} download "<URL>" --audio --json
   ```
2. Parse the returned JSON for `video_path` and `audio_path`.
3. Use the downloaded files for multimodal visual and audio inspection.
4. If an Instagram login is needed, instruct the user to run:
   ```bash
   python {REPO_ROOT / 'cli.py'} login --browser
   ```
"""
    try:
        rule_file.write_text(cursor_rule_content, encoding="utf-8")
        print(f"  ✅ Created Cursor rule at: {rule_file.resolve()}")
    except Exception as e:
        print(f"  ⚠️ Warning: Could not write cursor rule: {e}")

    return success


def install_codex(symlink: bool = False) -> bool:
    """Install skill to OpenAI Codex / Generic project agents (.agents/skills/media-downloader)."""
    target = REPO_ROOT / ".agents" / "skills" / "media-downloader"
    if target == SKILL_SOURCE:
        print(f"  ℹ️ Skill already exists at project root: {target.resolve()}")
        return True
    return copy_or_link_skill("Codex / .agents", target, symlink)


def copy_or_link_skill(agent_name: str, target: Path, symlink: bool = False) -> bool:
    """Copy or symlink skill directory to target destination."""
    print(f"📦 Installing for {agent_name} -> {target.resolve()}...")
    try:
        target.parent.mkdir(parents=True, exist_ok=True)

        if target.exists() or target.is_symlink():
            if target.is_dir() and not target.is_symlink():
                shutil.rmtree(target)
            else:
                target.unlink()

        if symlink:
            try:
                target.symlink_to(SKILL_SOURCE, target_is_directory=True)
                print(f"  🔗 Symlinked to {SKILL_SOURCE}")
                return True
            except (OSError, NotImplementedError):
                print("  ⚠️ Symlink privilege not available; falling back to copying files.")

        shutil.copytree(SKILL_SOURCE, target)
        print(f"  ✅ Successfully copied skill files to {target.resolve()}")
        return True
    except Exception as e:
        print(f"  ❌ Failed to install for {agent_name}: {e}")
        return False


def check_and_install_dependencies():
    """Verify and prompt to install python dependencies."""
    print("\n🔍 Checking Python dependencies...")
    reqs_file = REPO_ROOT / "requirements.txt"
    try:
        cmd = [sys.executable, "-m", "pip", "install", "-r", str(reqs_file)]
        print(f"Running: {' '.join(cmd)}")
        subprocess.check_call(cmd)
        print("✅ Python dependencies are up to date.")
    except Exception as e:
        print(f"⚠️ Warning: Could not auto-install dependencies: {e}")
        print(f"Please run manually: pip install -r {reqs_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Install Media Downloader as an AI Agent Skill for Cursor, Claude, Antigravity, or Codex",
    )
    parser.add_argument(
        "--agent",
        choices=["all", "antigravity", "claude", "cursor", "codex"],
        default="all",
        help="Target agent ecosystem (default: all)",
    )
    parser.add_argument(
        "--symlink",
        action="store_true",
        help="Use symlinks instead of copying (keeps skill auto-updated with git pull)",
    )
    parser.add_argument(
        "--skip-deps",
        action="store_true",
        help="Skip pip install requirements",
    )

    args = parser.parse_args()

    print(r"""
 ╔══════════════════════════════════════════════════════════════════╗
 ║  🤖 Media Downloader Skill Installer for AI Agents              ║
 ║  Compatible with Cursor, Claude Code, Codex, & Antigravity       ║
 ╚══════════════════════════════════════════════════════════════════╝
""")

    if not args.skip_deps:
        check_and_install_dependencies()

    print(f"\n🚀 Installing skill (Agent target: {args.agent.upper()})...\n")

    if args.agent == "all":
        install_antigravity(args.symlink)
        install_claude(args.symlink)
        install_cursor(args.symlink)
        install_codex(args.symlink)
    elif args.agent == "antigravity":
        install_antigravity(args.symlink)
    elif args.agent == "claude":
        install_claude(args.symlink)
    elif args.agent == "cursor":
        install_cursor(args.symlink)
    elif args.agent == "codex":
        install_codex(args.symlink)

    print("\n🎉 Skill installation complete!")
    print("\nTo test your installation, run:")
    print("    python cli.py status")
    print("    python cli.py download \"<any-instagram-reel-or-youtube-url>\" --audio --json")


if __name__ == "__main__":
    main()
