from django.db import migrations, models
import django.db.models.deletion


def forwards_create_curricula(apps, schema_editor):
    Program = apps.get_model("academics", "Program")
    ProgramCourse = apps.get_model("academics", "ProgramCourse")
    Curriculum = apps.get_model("academics", "Curriculum")
    CurriculumCourse = apps.get_model("academics", "CurriculumCourse")

    Enrollment = apps.get_model("students", "Enrollment")
    ResultBatch = apps.get_model("results", "ResultBatch")

    # Collect all (program_id, session_id) pairs that exist in real data
    pairs = set()

    for row in Enrollment.objects.values_list("program_id", "session_id"):
        if row[0] and row[1]:
            pairs.add((row[0], row[1]))

    for row in ResultBatch.objects.values_list("program_id", "session_id"):
        if row[0] and row[1]:
            pairs.add((row[0], row[1]))

    # Create curricula and copy program courses into each curriculum (same mapping for now)
    for program_id, session_id in sorted(pairs):
        try:
            program = Program.objects.get(pk=program_id)
        except Program.DoesNotExist:
            continue

        curriculum, _ = Curriculum.objects.get_or_create(
            program_id=program_id,
            session_id=session_id,
            defaults={
                "total_semesters": int(program.total_semesters),
                "is_active": True,
            },
        )

        # Keep total_semesters aligned if it was missing/zero
        if not curriculum.total_semesters:
            curriculum.total_semesters = int(program.total_semesters)
            curriculum.save(update_fields=["total_semesters"])

        # Copy ProgramCourse rows into CurriculumCourse for this curriculum
        for pc in ProgramCourse.objects.filter(program_id=program_id).values_list(
            "semester_number", "course_id"
        ):
            semester_number, course_id = pc
            CurriculumCourse.objects.get_or_create(
                curriculum_id=curriculum.id,
                semester_number=semester_number,
                course_id=course_id,
            )


def backwards_delete_curricula(apps, schema_editor):
    CurriculumCourse = apps.get_model("academics", "CurriculumCourse")
    Curriculum = apps.get_model("academics", "Curriculum")
    CurriculumCourse.objects.all().delete()
    Curriculum.objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ("academics", "0008_alter_program_unique_together"),
        ("students", "0002_department_fields"),
        ("results", "0004_resultbatch_department"),
    ]

    operations = [
        migrations.CreateModel(
            name="Curriculum",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("total_semesters", models.PositiveSmallIntegerField()),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("program", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="curricula", to="academics.program")),
                ("session", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="curricula", to="academics.session")),
            ],
            options={
                "ordering": ["-created_at"],
                "unique_together": {("program", "session")},
            },
        ),
        migrations.CreateModel(
            name="CurriculumCourse",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("semester_number", models.PositiveSmallIntegerField()),
                ("credit_hours_override", models.DecimalField(blank=True, decimal_places=1, max_digits=4, null=True)),
                ("course", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to="academics.course")),
                ("curriculum", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="curriculum_courses", to="academics.curriculum")),
            ],
            options={
                "ordering": ["semester_number", "course__code"],
                "unique_together": {("curriculum", "semester_number", "course")},
            },
        ),
        migrations.RunPython(forwards_create_curricula, backwards_delete_curricula),
    ]
