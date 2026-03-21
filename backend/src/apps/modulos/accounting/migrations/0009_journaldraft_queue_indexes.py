from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounting", "0008_operational_posting_config"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="journaldraft",
            index=models.Index(fields=["state", "generated_at", "id"], name="ix_acc_jdraft_state_ga_id"),
        ),
        migrations.AddIndex(
            model_name="journaldraft",
            index=models.Index(
                fields=["close_run_id", "state", "generated_at", "id"],
                name="ix_acc_jdraft_run_state_ga_id",
            ),
        ),
    ]
