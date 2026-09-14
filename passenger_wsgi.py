"""cPanel Passenger entrypoint. Point the Python App at this file."""

import os
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
os.chdir(BASE_DIR)
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from django.core.wsgi import get_wsgi_application

application = get_wsgi_application()
