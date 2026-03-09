from django.db import migrations, models


def forwards(apps, schema_editor):
    Program = apps.get_model("academics", "Program")
    Curriculum = apps.get_model("academics", "Curriculum")

    # Heuristic auto-fill for existing BS (2 Years) programs.
    # We keep it strict to avoid affecting non-BS 2-year programs (e.g., ADP).
    for p in Program.objects.all():
        try:
            if int(getattr(p, "semester_start", 1) or 1) != 1:
                continue
            total = int(getattr(p, "total_semesters", 0) or 0)
            name = (getattr(p, "name", "") or "").lower()
            if total == 4 and name.startswith("bs") and ("(2 years" in name or "2 years" in name):
                p.semester_start = 5
                p.save(update_fields=["semester_start"])
        except Exception:
            continue

    # Backfill curriculum semester_start from its program (snapshot).
    for c in Curriculum.objects.select_related("program").all():
        try:
            if int(getattr(c, "semester_start", 1) or 1) != 1:
                continue
            prog = getattr(c, "program", None)
            start = int(getattr(prog, "semester_start", 1) or 1) if prog else 1
            c.semester_start = start
            c.save(update_fields=["semester_start"])
        except Exception:
            continue


def backwards(apps, schema_editor):
    # Keep data as-is on rollback.
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0013_recalc_course_max_marks_20"),
    ]

    operations = [
        migrations.AddField(
            model_name="program",
            name="semester_start",
            field=models.PositiveSmallIntegerField(default=1),
        ),
        migrations.AddField(
            model_name="curriculum",
            name="semester_start",
            field=models.PositiveSmallIntegerField(default=1),
        ),
        migrations.RunPython(forwards, backwards),
    ]
