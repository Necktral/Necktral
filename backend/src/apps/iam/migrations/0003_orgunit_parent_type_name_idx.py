from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("iam", "0002_initial"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="orgunit",
            index=models.Index(fields=["parent", "unit_type", "name"], name="iam_orgunit_parent_type_name_idx"),
        ),
    ]
