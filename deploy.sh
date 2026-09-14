#!/bin/bash
set -euo pipefail

REPO_URL="https://github.com/mbaekimathi/fintech.git"
BRANCH="main"
APP_DIR="${APP_DIR:-$HOME/FIN}"

mkdir -p "$APP_DIR"
cd "$APP_DIR"

if [ -d .git ]; then
  echo "Repo already exists. Pulling latest..."
  git remote set-url origin "$REPO_URL"
  git pull origin "$BRANCH"
else
  echo "First time: cloning into this folder..."
  git clone -b "$BRANCH" "$REPO_URL" .
fi

if [ ! -f .env ]; then
  echo "Create .env from .env.example in $APP_DIR, then run this script again."
  exit 1
fi

python -m pip install -r requirements.txt
python manage.py migrate --noinput
python manage.py collectstatic --noinput

mkdir -p tmp
touch tmp/restart.txt

echo "Done. Pulled $BRANCH from $REPO_URL"
