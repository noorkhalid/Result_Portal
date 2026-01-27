from django.db import migrations, models
import django.db.models.deletion


DEFAULT_DEPT_NAME = "Falcon Educational Complex, Tank"


def forwards_create_and_attach(apps, schema_editor):
    Department = apps.get_model("academics", "Department")
    Program = apps.get_model("academics", "Program")
    ProgramCourse = apps.get_model("academics", "ProgramCourse")

    dept, _ = Department.objects.get_or_create(name=DEFAULT_DEPT_NAME)

    # Backfill existing Programs
    Program.objects.filter(department__isnull=True).update(department=dept)

    # Backfill existing ProgramCourse mappings
    ProgramCourse.objects.filter(department__isnull=True).update(department=dept)


def backwards_noop(apps, schema_editor):
    # We don't delete departments automatically on rollback.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0003_alter_course_code"),
    ]

    operations = [
        migrations.CreateModel(
            name="Department",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255, unique=True)),
            ],
            options={
                "ordering": ["name"],
            },
        ),
        migrations.AddField(
            model_name="program",
            name="department",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="programs", to="academics.department"),
        ),
        migrations.AddField(
            model_name="programcourse",
            name="department",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="program_courses", to="academics.department"),
        ),
        migrations.RunPython(forwards_create_and_attach, backwards_noop),
        migrations.AlterField(
            model_name="program",
            name="department",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="programs", to="academics.department"),
        ),
        migrations.AlterField(
            model_name="programcourse",
            name="department",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="program_courses", to="academics.department"),
        ),
    ]
