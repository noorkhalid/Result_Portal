from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("results", "0010_resultbatch_unique_per_department"),
    ]

    operations = [
        migrations.AddField(
            model_name="courseresult",
            name="sessional_marks",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Optional component marks (used for manual entry/import).",
                max_digits=6,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="courseresult",
            name="midterm_marks",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Optional component marks (used for manual entry/import).",
                max_digits=6,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="courseresult",
            name="terminal_marks",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                help_text="Optional component marks (used for manual entry/import).",
                max_digits=6,
                null=True,
            ),
        ),
    ]
