from django.db import migrations


def recalc_course_max_marks(apps, schema_editor):
    Course = apps.get_model("academics", "Course")

    for c in Course.objects.all().only("id", "credit_hours", "max_marks"):
        try:
            mm = int(round(float(c.credit_hours) * 20))
        except Exception:
            mm = 0
        if c.max_marks != mm:
            Course.objects.filter(id=c.id).update(max_marks=mm)


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0012_course_max_marks"),
    ]

    operations = [
        migrations.RunPython(recalc_course_max_marks, migrations.RunPython.noop),
    ]
