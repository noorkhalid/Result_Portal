from django.db import migrations, models


def seed_hold_categories(apps, schema_editor):
    HoldCategory = apps.get_model("results", "HoldCategory")
    SemesterResult = apps.get_model("results", "SemesterResult")
    ResultNotificationItem = apps.get_model("results", "ResultNotificationItem")

    seeded = {
        "dues": {"name": "RL Dues", "sort_order": 10, "is_active": True},
        "documents": {
            "name": "RL Documents",
            "sort_order": 20,
            "is_active": True,
        },
    }
    for code, defaults in seeded.items():
        HoldCategory.objects.update_or_create(code=code, defaults=defaults)

    existing_codes = set(
        SemesterResult.objects.exclude(hold_status__in=["", "none"])
        .values_list("hold_status", flat=True)
        .distinct()
    )
    existing_codes.update(
        ResultNotificationItem.objects.exclude(
            hold_status_snapshot__in=["", "none"]
        )
        .values_list("hold_status_snapshot", flat=True)
        .distinct()
    )

    for code in sorted(existing_codes):
        if not code or HoldCategory.objects.filter(code=code).exists():
            continue
        HoldCategory.objects.create(
            code=code,
            name=code.replace("-", " ").replace("_", " ").title(),
            is_active=False,
            sort_order=999,
        )


class Migration(migrations.Migration):

    dependencies = [
        ("results", "0015_protect_notification_history"),
    ]

    operations = [
        migrations.CreateModel(
            name="HoldCategory",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("code", models.SlugField(max_length=32, unique=True)),
                ("name", models.CharField(max_length=100, unique=True)),
                ("is_active", models.BooleanField(default=True)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
            ],
            options={
                "verbose_name_plural": "Hold categories",
                "ordering": ["sort_order", "name"],
            },
        ),
        migrations.AlterField(
            model_name="semesterresult",
            name="hold_status",
            field=models.CharField(default="none", max_length=32),
        ),
        migrations.AlterField(
            model_name="resultnotificationitem",
            name="hold_status_snapshot",
            field=models.CharField(default="none", max_length=32),
        ),
        migrations.RunPython(seed_hold_categories, migrations.RunPython.noop),
    ]
