from __future__ import annotations

from django.db import migrations, models


def _add_is_setup_complete_if_missing(apps, schema_editor):
    User = apps.get_model("accounts", "User")
    table = User._meta.db_table

    with schema_editor.connection.cursor() as cursor:
        columns = [
            c.name
            for c in schema_editor.connection.introspection.get_table_description(cursor, table)
        ]

    if "is_setup_complete" in columns:
        return

    field = models.BooleanField(default=False)
    field.set_attributes_from_name("is_setup_complete")
    schema_editor.add_field(User, field)


class Migration(migrations.Migration):
    dependencies = [
        ("accounts", "0002_user_must_change_password"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            # DB: agrega la columna solo si falta (para BD ya existentes no rompe).
            database_operations=[
                migrations.RunPython(_add_is_setup_complete_if_missing, migrations.RunPython.noop),
            ],
            # Estado: la columna forma parte del modelo.
            state_operations=[
                migrations.AddField(
                    model_name="user",
                    name="is_setup_complete",
                    field=models.BooleanField(default=False),
                ),
            ],
        )
    ]
