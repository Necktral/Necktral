from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("compras", "0001_initial"),
        ("parties", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="purchasedocument",
            name="supplier_party",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="purchase_documents",
                to="parties.party",
            ),
        ),
        migrations.AddIndex(
            model_name="purchasedocument",
            index=models.Index(
                fields=["company", "supplier_party"],
                name="ix_proc_doc_co_supp_party",
            ),
        ),
    ]
