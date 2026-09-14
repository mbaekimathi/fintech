"""
MySQL backend that still uses Django's official driver stack and PyMySQL.

Local XAMPP-style MariaDB 10.4 is older than Django 6's advertised floor
(10.11). We skip that gate so this hub can run on the installed server.
Use MySQL 8 or MariaDB 10.11+ in production.
"""

from django.db.backends.mysql.base import DatabaseWrapper as MySQLDatabaseWrapper


class DatabaseWrapper(MySQLDatabaseWrapper):
    def check_database_version_supported(self):
        return
