from __future__ import annotations

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("facturacion", "0006_billingdocument_payment_method"),
        ("parties", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="billingdocument",
            name="customer_party",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="billing_documents",
                to="parties.party",
            ),
        ),
        migrations.AddIndex(
            model_name="billingdocument",
            index=models.Index(
                fields=["company", "customer_party"],
                name="ix_bill_doc_co_cust_party",
            ),
        ),
    ]
