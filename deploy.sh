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
  git fetch origin "$BRANCH"
  git reset --hard "origin/$BRANCH"
else
  echo "First time: fetching into this existing folder..."
  if [ -f .env ]; then
    cp -a .env .env.keep
  fi
  git init
  git remote add origin "$REPO_URL"
  git fetch origin "$BRANCH"
  # cPanel Python App already created files here, so clone into '.' fails.
  find . -mindepth 1 -maxdepth 1 ! -name .git ! -name .env ! -name .env.keep -exec rm -rf {} +
  git checkout -f -B "$BRANCH" "origin/$BRANCH"
  if [ -f .env.keep ]; then
    mv -f .env.keep .env
  fi
fi

python -m pip install -r requirements.txt

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env. Set DB_PASSWORD in $APP_DIR/.env, then run this script again."
  exit 0
fi

python manage.py migrate --noinput
python manage.py collectstatic --noinput

mkdir -p tmp
touch tmp/restart.txt

echo "Done. Pulled $BRANCH from $REPO_URL"
