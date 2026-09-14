import pymysql

# Django 6 checks mysqlclient's version tuple. PyMySQL presents itself as
# MySQLdb after install_as_MySQLdb(); we advertise a compatible version so
# the official MySQL backend accepts the driver the project is required to use.
pymysql.version_info = (2, 2, 1, "final", 0)
pymysql.install_as_MySQLdb()
