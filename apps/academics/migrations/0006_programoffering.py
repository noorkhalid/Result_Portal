from django.db import migrations, models
import django.db.models.deletion


def forwards_create_default_offerings(apps, schema_editor):
    """Create ProgramOffering rows for existing Program.department values.

    This keeps existing data working immediately after adding ProgramOffering.
    """
    Program = apps.get_model("academics", "Program")
    ProgramOffering = apps.get_model("academics", "ProgramOffering")

    for p in Program.objects.all().only("id", "department_id"):
        if p.department_id:
            ProgramOffering.objects.get_or_create(
                department_id=p.department_id,
                program_id=p.id,
                defaults={"is_active": True},
            )


def backwards_delete_default_offerings(apps, schema_editor):
    # On reverse migration, just delete all offerings.
    ProgramOffering = apps.get_model("academics", "ProgramOffering")
    ProgramOffering.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0005_alter_course_title"),
    ]

    operations = [
        migrations.CreateModel(
            name="ProgramOffering",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("is_active", models.BooleanField(default=True)),
                (
                    "department",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="program_offerings",
                        to="academics.department",
                    ),
                ),
                (
                    "program",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="offerings",
                        to="academics.program",
                    ),
                ),
            ],
            options={
                "ordering": ["department__name", "program__name"],
                "unique_together": {("department", "program")},
            },
        ),
        migrations.RunPython(forwards_create_default_offerings, backwards_delete_default_offerings),
    ]
