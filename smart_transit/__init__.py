import pymysql
pymysql.install_as_MySQLdb()

# Allow MariaDB 10.4 compatibility with Django 5.2
from django.db.backends.base.base import BaseDatabaseWrapper
BaseDatabaseWrapper.check_database_version_supported = lambda self: None

from django.db.backends.mysql.features import DatabaseFeatures
DatabaseFeatures.can_return_columns_from_insert = property(lambda self: False)
