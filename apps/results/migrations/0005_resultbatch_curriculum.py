from django.db import migrations, models
import django.db.models.deletion


def forwards_attach_curriculum(apps, schema_editor):
    Curriculum = apps.get_model("academics", "Curriculum")
    ResultBatch = apps.get_model("results", "ResultBatch")

    for batch in ResultBatch.objects.filter(curriculum__isnull=True).only("id", "program_id", "session_id"):
        if not batch.program_id or not batch.session_id:
            continue
        cur = Curriculum.objects.filter(program_id=batch.program_id, session_id=batch.session_id).first()
        if cur:
            ResultBatch.objects.filter(pk=batch.pk).update(curriculum_id=cur.id)


def backwards_detach_curriculum(apps, schema_editor):
    ResultBatch = apps.get_model("results", "ResultBatch")
    ResultBatch.objects.update(curriculum_id=None)


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0009_curriculum_by_session"),
        ("results", "0004_resultbatch_department"),
    ]

    operations = [
        migrations.AddField(
            model_name="resultbatch",
            name="curriculum",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.PROTECT,
                related_name="result_batches",
                to="academics.curriculum",
            ),
        ),
        migrations.RunPython(forwards_attach_curriculum, backwards_detach_curriculum),
    ]
