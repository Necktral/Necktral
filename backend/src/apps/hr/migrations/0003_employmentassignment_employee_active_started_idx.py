from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("hr", "0002_remove_positionrolemap_hr_positionrolemap_position_isactive_idx_and_more"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="employmentassignment",
            index=models.Index(
                fields=["employee", "is_active", "started_at"],
                name="hr_employassign_emp_active_start_idx",
            ),
        ),
    ]
