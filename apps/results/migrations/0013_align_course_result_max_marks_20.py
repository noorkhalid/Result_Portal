from django.db import migrations


def align_max_marks(apps, schema_editor):
    CourseResult = apps.get_model("results", "CourseResult")
    Course = apps.get_model("academics", "Course")

    course_map = {c.id: c.max_marks for c in Course.objects.all().only("id", "max_marks")}

    for cr in CourseResult.objects.all().only("id", "course_id", "max_marks"):
        mm = course_map.get(cr.course_id)
        if mm is None:
            continue
        if cr.max_marks != mm:
            CourseResult.objects.filter(id=cr.id).update(max_marks=mm)


class Migration(migrations.Migration):

    dependencies = [
        ("results", "0012_align_course_result_max_marks"),
        ("academics", "0013_recalc_course_max_marks_20"),
    ]

    operations = [
        migrations.RunPython(align_max_marks, migrations.RunPython.noop),
    ]
