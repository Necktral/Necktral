from __future__ import annotations

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("facturacion", "0004_billingdocument_source_refs"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="billingdocument",
            name="uniq_bill_number",
        ),
        migrations.AddConstraint(
            model_name="billingdocument",
            constraint=models.UniqueConstraint(
                fields=["company", "branch", "doc_type", "series", "number"],
                condition=models.Q(number__gt=0),
                name="uniq_bill_number",
            ),
        ),
    ]
