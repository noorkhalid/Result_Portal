from django.db import models

from academics.models import (
    Department,
    Program,
    Session,
    Course,
    Curriculum,
    get_default_department,
)
from students.models import Enrollment


class ExamType(models.Model):
    """Configurable exam/result type (e.g. Regular, Repeat, Improved)."""

    code = models.SlugField(max_length=32, unique=True)
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    class Meta:
        ordering = ["sort_order", "name"]

    def __str__(self) -> str:
        return self.name


def get_default_exam_type() -> "ExamType":
    """Safe fallback used by forms/seeded data."""

    obj, _ = ExamType.objects.get_or_create(code="regular", defaults={"name": "Regular", "sort_order": 1})
    return obj


class GradeScale(models.Model):
    min_percentage = models.DecimalField(max_digits=5, decimal_places=2)
    max_percentage = models.DecimalField(max_digits=5, decimal_places=2)
    letter_grade = models.CharField(max_length=5)
    grade_point = models.DecimalField(max_digits=4, decimal_places=2)
    remarks = models.CharField(max_length=50, default="Pass")
    is_fail = models.BooleanField(default=False)

    class Meta:
        ordering = ["-min_percentage"]

    def __str__(self):
        return (
            f"{self.min_percentage}-{self.max_percentage}: "
            f"{self.letter_grade} ({self.grade_point})"
        )


class ResultBatch(models.Model):
    """
    A result event for a program+session+semester.
    """

    department = models.ForeignKey(
        Department, on_delete=models.PROTECT, related_name="result_batches"
    )

    program = models.ForeignKey(Program, on_delete=models.PROTECT)
    session = models.ForeignKey(Session, on_delete=models.PROTECT)

    curriculum = models.ForeignKey(
        Curriculum,
        on_delete=models.PROTECT,
        related_name="result_batches",
    )

    semester_number = models.PositiveSmallIntegerField()

    exam_type = models.ForeignKey(
        ExamType,
        on_delete=models.PROTECT,
        related_name="result_batches",
    )

    notification_no = models.CharField(max_length=100, blank=True)
    notification_date = models.DateField(null=True, blank=True)

    is_locked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("program", "session", "semester_number", "exam_type")
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        # Department fallback
        if not self.department_id:
            self.department = get_default_department()

        # Exam type fallback
        if not getattr(self, "exam_type_id", None):
            self.exam_type = get_default_exam_type()

        # Auto-attach curriculum if missing
        if not self.curriculum_id and self.program_id and self.session_id:
            curriculum, _ = Curriculum.objects.get_or_create(
                program_id=self.program_id,
                session_id=self.session_id,
                defaults={"total_semesters": self.program.total_semesters},
            )
            self.curriculum = curriculum

        # ✅ STEP 2.2-B VALIDATION
        if (
            self.curriculum.program_id != self.program_id
            or self.curriculum.session_id != self.session_id
        ):
            raise ValueError(
                "ResultBatch curriculum must match program and session"
            )

        super().save(*args, **kwargs)

    def __str__(self):
        return (
            f"{self.program} | {self.session.start_year} | "
            f"Sem {self.semester_number} | {self.exam_type.code}"
        )


class CourseResult(models.Model):
    batch = models.ForeignKey(
        ResultBatch, on_delete=models.CASCADE, related_name="course_results"
    )
    enrollment = models.ForeignKey(
        Enrollment, on_delete=models.PROTECT, related_name="course_results"
    )
    course = models.ForeignKey(Course, on_delete=models.PROTECT)

    marks_obtained = models.DecimalField(max_digits=6, decimal_places=2)
    max_marks = models.DecimalField(max_digits=6, decimal_places=2, default=100)

    percentage = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    letter_grade = models.CharField(max_length=5, blank=True)
    grade_point = models.DecimalField(max_digits=4, decimal_places=2, default=0)

    class Meta:
        unique_together = ("batch", "enrollment", "course")

    def __str__(self):
        return f"{self.enrollment.roll_no} | {self.course.code}"


class SemesterResult(models.Model):
    batch = models.ForeignKey(
        ResultBatch, on_delete=models.CASCADE, related_name="semester_results"
    )
    enrollment = models.ForeignKey(
        Enrollment, on_delete=models.PROTECT, related_name="semester_results"
    )

    total_obtained = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    total_max = models.DecimalField(max_digits=8, decimal_places=2, default=0)
    percentage = models.DecimalField(max_digits=6, decimal_places=2, default=0)

    gpa = models.DecimalField(max_digits=4, decimal_places=2, default=0)
    cgpa = models.DecimalField(max_digits=4, decimal_places=2, default=0)

    letter_grade = models.CharField(max_length=5, blank=True)
    remarks = models.CharField(max_length=200, blank=True)
    subjects_to_reappear = models.TextField(blank=True)

    class Meta:
        unique_together = ("batch", "enrollment")

    def __str__(self):
        return f"{self.enrollment.roll_no} | Sem {self.batch.semester_number}"
