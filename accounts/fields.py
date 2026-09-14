from django.db import models


class MysqlChoiceEnumField(models.CharField):
    """CharField stored as MySQL ENUM so database tools show a dropdown."""

    def db_type(self, connection):
        if connection.vendor == "mysql":
            members = ",".join(
                "'%s'" % str(value).replace("'", "''") for value, _label in self.choices
            )
            return f"enum({members})"
        return super().db_type(connection)


class MysqlBooleanEnumField(models.BooleanField):
    """Boolean stored as MySQL ENUM('0','1') so database tools show a dropdown."""

    def db_type(self, connection):
        if connection.vendor == "mysql":
            return "enum('0','1')"
        return super().db_type(connection)

    def get_db_prep_value(self, value, connection, prepared=False):
        if value is None:
            return None
        value = self.to_python(value)
        if connection.vendor == "mysql":
            return "1" if value else "0"
        return 1 if value else 0

    def from_db_value(self, value, expression, connection):
        if value is None:
            return None
        if isinstance(value, bool):
            return value
        return self.to_python(value)
