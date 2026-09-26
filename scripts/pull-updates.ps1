# Pull latest changes from GitHub (git pull).
#   .\scripts\pull-updates.ps1

$ErrorActionPreference = "Stop"

$AppDir = Split-Path -Parent $PSScriptRoot
$RepoUrl = if ($env:REPO_URL) { $env:REPO_URL } else { "https://github.com/mbaekimathi/fintech.git" }
$Branch = if ($env:BRANCH) { $env:BRANCH } else { "main" }

Set-Location $AppDir

if (-not (Test-Path ".git")) {
    Write-Error "Not a git repo: $AppDir"
}

git remote set-url origin $RepoUrl
git pull origin $Branch

$Head = git rev-parse --short HEAD
Write-Host "Up to date at $Head ($Branch)"
