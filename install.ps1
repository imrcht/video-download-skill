# Media Downloader Skill Installer for Windows PowerShell
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

Write-Host "🤖 Installing Media Downloader Agent Skill on Windows..." -ForegroundColor Cyan
python install.py @args
