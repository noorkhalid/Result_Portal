from django.db import migrations, models
import django.db.models.deletion


def forwards_attach_curriculum(apps, schema_editor):
    Curriculum = apps.get_model("academics", "Curriculum")
    Enrollment = apps.get_model("students", "Enrollment")

    for enr in Enrollment.objects.filter(curriculum__isnull=True).only("id", "program_id", "session_id"):
        if not enr.program_id or not enr.session_id:
            continue
        cur = Curriculum.objects.filter(program_id=enr.program_id, session_id=enr.session_id).first()
        if cur:
            Enrollment.objects.filter(pk=enr.pk).update(curriculum_id=cur.id)


def backwards_detach_curriculum(apps, schema_editor):
    Enrollment = apps.get_model("students", "Enrollment")
    Enrollment.objects.update(curriculum_id=None)


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0009_curriculum_by_session"),
        ("students", "0002_department_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="enrollment",
            name="curriculum",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="enrollments",
                to="academics.curriculum",
            ),
        ),
        migrations.RunPython(forwards_attach_curriculum, backwards_detach_curriculum),
    ]
