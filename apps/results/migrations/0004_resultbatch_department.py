from django.db import migrations, models
import django.db.models.deletion


DEFAULT_DEPT_NAME = "Falcon Educational Complex, Tank"


def forwards_attach_department(apps, schema_editor):
    Department = apps.get_model("academics", "Department")
    Program = apps.get_model("academics", "Program")
    ResultBatch = apps.get_model("results", "ResultBatch")

    dept, _ = Department.objects.get_or_create(name=DEFAULT_DEPT_NAME)

    # First: set department from program.department whenever possible.
    for batch in ResultBatch.objects.select_related("program").all():
        try:
            program = Program.objects.get(pk=batch.program_id)
            batch.department_id = program.department_id or dept.id
        except Program.DoesNotExist:
            batch.department_id = dept.id
        batch.save(update_fields=["department"])


def backwards_noop(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0004_department_and_org_fields"),
        ("results", "0003_semesterresult_percentage_semesterresult_total_max_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="resultbatch",
            name="department",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="result_batches",
                to="academics.department",
            ),
        ),
        migrations.RunPython(forwards_attach_department, backwards_noop),
        migrations.AlterField(
            model_name="resultbatch",
            name="department",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="result_batches",
                to="academics.department",
            ),
        ),
    ]
