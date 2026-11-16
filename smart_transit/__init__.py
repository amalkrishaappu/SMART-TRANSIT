import pymysql
pymysql.install_as_MySQLdb()

# Allow MariaDB 10.4.32 compatibility with Django 5.2
from django.db.backends.base.base import BaseDatabaseWrapper
BaseDatabaseWrapper.check_database_version_supported = lambda self: None
