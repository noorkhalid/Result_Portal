from django.db import migrations, models


def populate_course_max_marks(apps, schema_editor):
    Course = apps.get_model("academics", "Course")
    for c in Course.objects.all().only("id", "credit_hours"):
        try:
            max_marks = int(round(float(c.credit_hours) * 20))
        except Exception:
            max_marks = 0
        Course.objects.filter(id=c.id).update(max_marks=max_marks)


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0011_remove_programcourse"),
    ]

    operations = [
        migrations.AddField(
            model_name="course",
            name="max_marks",
            field=models.PositiveSmallIntegerField(default=0, editable=False),
        ),
        migrations.RunPython(populate_course_max_marks, migrations.RunPython.noop),
    ]
