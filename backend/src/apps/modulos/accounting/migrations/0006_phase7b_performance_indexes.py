from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("accounting", "0005_phase7b_intercompany_consolidation"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="intercompanytransaction",
            index=models.Index(
                fields=["source_company", "status", "created_at"],
                name="acc_ic_src_status_created_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="intercompanytransaction",
            index=models.Index(
                fields=["target_company", "status", "created_at"],
                name="acc_ic_tgt_status_created_idx",
            ),
        ),
    ]
