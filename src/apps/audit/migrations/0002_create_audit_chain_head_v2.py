from django.db import migrations, models

class Migration(migrations.Migration):
    dependencies = [
        ("audit", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="AuditChainHeadV2",
            fields=[
                ("partition_key", models.CharField(max_length=64, primary_key=True, serialize=False)),
                ("last_event_hash", models.CharField(blank=True, default="", max_length=64)),
                ("updated_at", models.DateTimeField(auto_now=True)),
            ],
        ),
    ]
