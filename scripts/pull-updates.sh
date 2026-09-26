#!/usr/bin/env bash
# Pull latest changes from GitHub (git pull).
#   bash scripts/pull-updates.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
REPO_URL="${REPO_URL:-https://github.com/mbaekimathi/fintech.git}"
BRANCH="${BRANCH:-main}"

cd "$APP_DIR"

if [ ! -d .git ]; then
  echo "Not a git repo: $APP_DIR"
  exit 1
fi

git remote set-url origin "$REPO_URL"
git pull origin "$BRANCH"

echo "Up to date at $(git rev-parse --short HEAD) ($BRANCH)"
