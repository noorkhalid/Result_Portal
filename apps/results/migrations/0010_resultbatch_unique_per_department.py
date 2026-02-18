from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("results", "0009_rl_holds_and_notifications"),
    ]

    operations = [
        migrations.AlterUniqueTogether(
            name="resultbatch",
            unique_together={(
                "department",
                "program",
                "session",
                "semester_number",
                "exam_type",
            )},
        ),
    ]
