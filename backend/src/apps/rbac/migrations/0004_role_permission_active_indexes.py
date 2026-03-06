from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("rbac", "0003_rename_rbac_roleas_origin_isactive_idx_rbac_roleas_origin_7700cc_idx"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="role",
            index=models.Index(fields=["is_active", "name"], name="rbac_role_active_name_idx"),
        ),
        migrations.AddIndex(
            model_name="permission",
            index=models.Index(fields=["is_active", "code"], name="rbac_perm_active_code_idx"),
        ),
    ]
