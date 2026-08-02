import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("results", "0014_notification_foundation"),
    ]

    operations = [
        migrations.AlterField(
            model_name="resultnotification",
            name="batch",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="notifications",
                to="results.resultbatch",
            ),
        ),
        migrations.AlterField(
            model_name="resultnotificationitem",
            name="semester_result",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="notification_items",
                to="results.semesterresult",
            ),
        ),
    ]
