# NEXUS Ledger

Central paybill and accounts hub for every product you run. Staff sign in with a 6-digit staff code and a 6-digit password. Sister systems post collections through a hashed API key.

## What is in the first cut

- Responsive workspace (phone, tablet, desktop) with one header, sidebar, footer, and page frame
- Roles: Admin, Manager, Employee, Client, Accounts, IT Support
- Employee self-registration (account stays locked until an admin or manager approves it)
- Django 5.0 (fits MariaDB 10.4 / XAMPP; Django 6 needs MariaDB 10.11+), Django REST Framework, django-axes lockout, Argon2 hashing
- MySQL / MariaDB through **PyMySQL**
- API for connected systems: health, paybill catalog, ledger ingest, ledger list

## Security already wired

- Passwords are hashed (never stored in plain text)
- CSRF on every form, httponly session and CSRF cookies
- Five failed logins lock that staff code + IP for one hour
- Unapproved employees cannot enter the workspace
- Integration keys are stored as SHA-256 hashes and shown only once
- Clickjacking, MIME sniffing, and referrer policies are set
- Turn on `DJANGO_SECURE_SSL=True` behind HTTPS in production

A 6-digit password is a business rule, not a strong secret. The lockout, hashing, and approval gate exist because of that. Change `DJANGO_SECRET_KEY` before any real deployment.

## Setup

1. Create the MySQL database:

```sql
CREATE DATABASE fintech_paybill CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
```

2. Copy environment values:

```powershell
copy .env.example .env
```

3. Edit `.env` with your MySQL user and password.

4. Install and migrate:

```powershell
python -m pip install -r requirements.txt
python manage.py migrate
python manage.py bootstrap --code 100001 --password 135790 --email admin@yourdomain.com
python manage.py runserver
```

Open [http://127.0.0.1:8000/login/](http://127.0.0.1:8000/login/).

## Host on cPanel (git pull)

Point the Python App at `~/FIN`. After that, updates are one script: clone or pull [mbaekimathi/fintech](https://github.com/mbaekimathi/fintech.git), install, migrate, collectstatic, restart.

First time, create MySQL, create `~/FIN/.env` from `.env.example`, then in the Python App terminal:

```bash
bash deploy.sh
```

Or paste this (same as `deploy.sh`). It works even when cPanel has already created files in `~/FIN`:

```bash
cd ~/FIN
REPO_URL="https://github.com/mbaekimathi/fintech.git"

if [ -d .git ]; then
  echo "Repo already exists. Pulling latest..."
  git remote set-url origin "$REPO_URL"
  git fetch origin main
  git reset --hard origin/main
else
  echo "First time: fetching into this existing folder..."
  [ -f .env ] && cp -a .env .env.keep
  git init
  git remote add origin "$REPO_URL"
  git fetch origin main
  find . -mindepth 1 -maxdepth 1 ! -name .git ! -name .env ! -name .env.keep -exec rm -rf {} +
  git checkout -f -B main origin/main
  [ -f .env.keep ] && mv -f .env.keep .env
fi

pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
mkdir -p tmp && touch tmp/restart.txt
```

`.env` is kept if you already created it. Later runs only fetch and reset to `main`.

Python App settings:

- Python 3.11 or 3.12 (3.13 is newer than this Django 5.0 stack)
- Application root = `~/FIN`
- Startup file = `passenger_wsgi.py`
- Entry point = `application`

Production `.env` values:

```
DJANGO_DEBUG=False
DJANGO_SECRET_KEY=<long-random-string>
DJANGO_ALLOWED_HOSTS=yourdomain.com,www.yourdomain.com
DJANGO_CSRF_TRUSTED_ORIGINS=https://yourdomain.com,https://www.yourdomain.com
DJANGO_SECURE_SSL=True
DARAJA_PUBLIC_BASE_URL=https://yourdomain.com
DB_NAME=<cpanel database name>
DB_USER=<cpanel database user>
DB_PASSWORD=<cpanel database password>
DB_HOST=localhost
DB_PORT=3306
```

First login only:

```bash
python manage.py bootstrap --code 100001 --password 135790 --email admin@yourdomain.com
```

Then change that password and paste Daraja credentials under **Settings → Daraja**. If cPanel overwrites `passenger_wsgi.py`, restore this repo’s file and run `bash deploy.sh` again.

Default bootstrap admin (change immediately):

- Staff code: `100001`
- Password: `135790`

`bootstrap` also prints a one-time API key for the sample **Flagship POS** system. To mint another key later:

```powershell
python manage.py issue_api_key --system flagship-pos --name pos-desk
```

This machine is on MariaDB 10.4. Django 6 refuses that version, so the project stays on Django 5.0 until you upgrade the database server. PyMySQL is still the driver.

## Register as an employee

From the login page use **Register as an employee**. Save the staff code shown on the next screen. An Admin or Manager approves the person under **People**.

## Connect another system

Send:

```
X-API-Key: <the key from bootstrap or admin>
```

| Method | Path | Purpose |
| --- | --- | --- |
| GET | `/api/v1/health/` | Liveness |
| GET | `/api/v1/paybills/` | Paybills mapped to that system |
| POST | `/api/v1/ledger/ingest/` | Post a collection |
| GET | `/api/v1/ledger/` | Read that system's ledger |

Example ingest body:

```json
{
  "reference": "POS-10021",
  "paybill_number": "888555",
  "amount": "2500.00",
  "currency": "KES",
  "payer_name": "Jane Wanjiku",
  "payer_phone": "254711000111",
  "account_ref": "INV-88",
  "status": "COMPLETED"
}
```

## Project layout

- `accounts` — users, 6-digit login, roles, approval
- `core` — shared shell and dashboard
- `paybill` — paybill accounts, connected systems, ledger
- `integrations` — API keys and REST endpoints
- `templates` / `static` — one layout used on every signed-in page
