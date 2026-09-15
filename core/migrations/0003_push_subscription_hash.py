# Generated manually for MySQL-safe unique endpoint storage.

import hashlib

from django.db import migrations, models


def fill_endpoint_hashes(apps, schema_editor):
    PushSubscription = apps.get_model("core", "PushSubscription")
    for row in PushSubscription.objects.all():
        row.endpoint_hash = hashlib.sha256((row.endpoint or "").encode("utf-8")).hexdigest()
        row.save(update_fields=["endpoint_hash"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0002_push_subscription"),
    ]

    operations = [
        migrations.AddField(
            model_name="pushsubscription",
            name="endpoint_hash",
            field=models.CharField(blank=True, default="", max_length=64),
        ),
        migrations.AlterField(
            model_name="pushsubscription",
            name="endpoint",
            field=models.TextField(),
        ),
        migrations.RunPython(fill_endpoint_hashes, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="pushsubscription",
            name="endpoint_hash",
            field=models.CharField(max_length=64, unique=True),
        ),
    ]
