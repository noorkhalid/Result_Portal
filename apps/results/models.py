from django.db import models
from django.core.exceptions import ValidationError

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
        # A batch is unique **per department**.
        # Same program+session+semester+exam_type can exist in multiple departments.
        unique_together = (
            "department",
            "program",
            "session",
            "semester_number",
            "exam_type",
        )
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

    # -----------------------------
    # Marks entry
    # -----------------------------
    # Backward compatible: old data may have only `marks_obtained`.
    # If any component marks are provided, `marks_obtained` is derived.
    sessional_marks = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Optional component marks (used for manual entry/import).",
    )
    midterm_marks = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Optional component marks (used for manual entry/import).",
    )
    terminal_marks = models.DecimalField(
        max_digits=6,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Optional component marks (used for manual entry/import).",
    )

    marks_obtained = models.DecimalField(max_digits=6, decimal_places=2)
    max_marks = models.DecimalField(max_digits=6, decimal_places=2, default=100)

    percentage = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    letter_grade = models.CharField(max_length=5, blank=True)
    grade_point = models.DecimalField(max_digits=4, decimal_places=2, default=0)

    class Meta:
        unique_together = ("batch", "enrollment", "course")

    def clean(self):
        """Safety checks so results can never be saved in the wrong batch."""
        super().clean()
        if self.batch_id and self.enrollment_id:
            # Department must match
            if self.enrollment.department_id != self.batch.department_id:
                raise ValidationError(
                    {"batch": "Batch department must match the student's enrollment department."}
                )

            # Program + Session must match
            if self.enrollment.program_id != self.batch.program_id:
                raise ValidationError(
                    {"batch": "Batch program must match the student's enrollment program."}
                )
            if self.enrollment.session_id != self.batch.session_id:
                raise ValidationError(
                    {"batch": "Batch session must match the student's enrollment session."}
                )

    def save(self, *args, **kwargs):
        # Enforce constraints at model-level (prevents future import bugs)
        # If any component marks are present, derive total.
        if (
            self.sessional_marks is not None
            or self.midterm_marks is not None
            or self.terminal_marks is not None
        ):
            s = self.sessional_marks or 0
            m = self.midterm_marks or 0
            t = self.terminal_marks or 0
            self.marks_obtained = (s + m + t)
        self.full_clean()
        return super().save(*args, **kwargs)

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

    # -----------------------------
    # Result Hold (RL) – per batch/semester
    # -----------------------------
    HOLD_NONE = "none"
    HOLD_DUES = "dues"
    HOLD_DOCUMENTS = "documents"

    HOLD_CHOICES = (
        (HOLD_NONE, "None"),
        (HOLD_DUES, "RL Dues"),
        (HOLD_DOCUMENTS, "RL Documents"),
    )

    hold_status = models.CharField(
        max_length=16,
        choices=HOLD_CHOICES,
        default=HOLD_NONE,
    )
    hold_note = models.CharField(max_length=255, blank=True)
    hold_cleared_at = models.DateTimeField(null=True, blank=True)
    hold_cleared_by = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="cleared_semester_holds",
    )

    class Meta:
        unique_together = ("batch", "enrollment")

    def clean(self):
        """Safety checks so semester results can never be saved in the wrong batch."""
        super().clean()
        if self.batch_id and self.enrollment_id:
            if self.enrollment.department_id != self.batch.department_id:
                raise ValidationError(
                    {"batch": "Batch department must match the student's enrollment department."}
                )
            if self.enrollment.program_id != self.batch.program_id:
                raise ValidationError(
                    {"batch": "Batch program must match the student's enrollment program."}
                )
            if self.enrollment.session_id != self.batch.session_id:
                raise ValidationError(
                    {"batch": "Batch session must match the student's enrollment session."}
                )

    def save(self, *args, **kwargs):
        # Enforce constraints at model-level (prevents future import bugs)
        self.full_clean()
        return super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.enrollment.roll_no} | Sem {self.batch.semester_number}"


class ResultNotification(models.Model):
    """A printable notification for a ResultBatch.

    A batch may have multiple notifications:
      - initial (full) notification
      - later clearance notifications for held students
    """

    batch = models.ForeignKey(
        ResultBatch, on_delete=models.CASCADE, related_name="notifications"
    )

    notification_no = models.CharField(max_length=100)
    notification_date = models.DateField()

    # Declaration date is fixed per batch (set on first notification; reused later)
    declaration_date = models.DateField()

    remarks = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        return f"{self.batch} | {self.notification_no}"


class ResultNotificationItem(models.Model):
    """One student row included in a ResultNotification."""

    notification = models.ForeignKey(
        ResultNotification, on_delete=models.CASCADE, related_name="items"
    )
    semester_result = models.ForeignKey(
        SemesterResult, on_delete=models.CASCADE, related_name="notification_items"
    )

    hold_status_snapshot = models.CharField(
        max_length=16,
        choices=SemesterResult.HOLD_CHOICES,
        default=SemesterResult.HOLD_NONE,
    )

    class Meta:
        unique_together = ("notification", "semester_result")

    def __str__(self) -> str:
        return f"{self.notification_id} | {self.semester_result_id}"
