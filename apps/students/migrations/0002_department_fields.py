from django.db import migrations, models
import django.db.models.deletion


DEFAULT_DEPT_NAME = "Falcon Educational Complex, Tank"


def forwards_attach_department(apps, schema_editor):
    Department = apps.get_model("academics", "Department")
    Student = apps.get_model("students", "Student")
    Enrollment = apps.get_model("students", "Enrollment")

    dept, _ = Department.objects.get_or_create(name=DEFAULT_DEPT_NAME)

    Student.objects.filter(department__isnull=True).update(department=dept)
    Enrollment.objects.filter(department__isnull=True).update(department=dept)


def backwards_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0004_department_and_org_fields"),
        ("students", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="student",
            name="department",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="students", to="academics.department"),
        ),
        migrations.AddField(
            model_name="enrollment",
            name="department",
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="enrollments", to="academics.department"),
        ),
        migrations.RunPython(forwards_attach_department, backwards_noop),
        migrations.AlterField(
            model_name="student",
            name="department",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="students", to="academics.department"),
        ),
        migrations.AlterField(
            model_name="enrollment",
            name="department",
            field=models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="enrollments", to="academics.department"),
        ),
    ]
