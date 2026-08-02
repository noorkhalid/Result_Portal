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


class HoldCategoryQuerySet(models.QuerySet):
    def delete(self):
        for category in self:
            if category.is_in_use:
                raise ValidationError(
                    "This hold category is already used in results or notification history. "
                    "Deactivate it instead of deleting it."
                )
        return super().delete()


class HoldCategory(models.Model):
    """Database-managed result hold category (for example RL Dues)."""

    code = models.SlugField(max_length=32, unique=True)
    name = models.CharField(max_length=100, unique=True)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveSmallIntegerField(default=0)

    objects = HoldCategoryQuerySet.as_manager()

    class Meta:
        ordering = ["sort_order", "name"]
        verbose_name_plural = "Hold categories"

    def clean(self):
        super().clean()
        self.code = (self.code or "").strip().lower()
        self.name = (self.name or "").strip()
        if self.code == "none":
            raise ValidationError({"code": 'The reserved code "none" cannot be used.'})

        if self.pk:
            previous_code = (
                HoldCategory.objects.filter(pk=self.pk)
                .values_list("code", flat=True)
                .first()
            )
            if previous_code and previous_code != self.code:
                if (
                    SemesterResult.objects.filter(hold_status=previous_code).exists()
                    or ResultNotificationItem.objects.filter(
                        hold_status_snapshot=previous_code
                    ).exists()
                ):
                    raise ValidationError(
                        {"code": "The code cannot be changed because this category is already in use."}
                    )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def is_in_use(self) -> bool:
        return (
            SemesterResult.objects.filter(hold_status=self.code).exists()
            or ResultNotificationItem.objects.filter(
                hold_status_snapshot=self.code
            ).exists()
        )

    def delete(self, *args, **kwargs):
        if self.is_in_use:
            raise ValidationError(
                "This hold category is already used in results or notification history. "
                "Deactivate it instead of deleting it."
            )
        return super().delete(*args, **kwargs)

    def __str__(self) -> str:
        return self.name


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

    # Permanent date set by the first Full Result Notification.
    # It remains unchanged even when later clearance notifications are issued.
    official_result_declaration_date = models.DateField(
        null=True,
        blank=True,
        editable=False,
    )

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

    @property
    def is_final_semester(self) -> bool:
        sem_end = int(getattr(self.curriculum, "semester_end", 0) or 0)
        if not sem_end:
            sem_end = int(getattr(self.program, "semester_end", 0) or 0)
        return bool(sem_end and int(self.semester_number) == sem_end)

    def save(self, *args, **kwargs):
        if self.pk:
            previous_date = (
                ResultBatch.objects.filter(pk=self.pk)
                .values_list("official_result_declaration_date", flat=True)
                .first()
            )
            update_fields = kwargs.get("update_fields")
            date_is_being_saved = (
                update_fields is None
                or "official_result_declaration_date" in update_fields
            )
            if previous_date:
                if (
                    date_is_being_saved
                    and self.official_result_declaration_date not in (None, previous_date)
                ):
                    raise ValidationError(
                        "The official result declaration date cannot be changed once set."
                    )
                # Protect stale model instances from clearing the permanent date.
                self.official_result_declaration_date = previous_date

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
                defaults={
                    "total_semesters": self.program.total_semesters,
                    "semester_start": getattr(self.program, "semester_start", 1) or 1,
                },
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

        # Semester number must fall within the curriculum's semester span.
        sem_start = int(getattr(self.curriculum, "semester_start", 1) or 1)
        sem_end = int(getattr(self.curriculum, "semester_end", 0) or 0)
        if sem_end and (int(self.semester_number) < sem_start or int(self.semester_number) > sem_end):
            raise ValueError(
                f"Semester number {self.semester_number} is out of range ({sem_start}-{sem_end}) for this curriculum"
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
        # Keep max marks aligned with the course rule (credit_hours × 10).
        try:
            course_max = getattr(self.course, "max_marks", None)
            if course_max is not None:
                self.max_marks = course_max
        except Exception:
            pass

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

    # Legacy constants remain for backward compatibility with existing data and
    # callers. Assignable categories are loaded from HoldCategory.
    hold_status = models.CharField(
        max_length=32,
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
        self.hold_status = (self.hold_status or self.HOLD_NONE).strip().lower()
        if self.hold_status != self.HOLD_NONE:
            category = HoldCategory.objects.filter(code=self.hold_status).first()
            if not category:
                raise ValidationError(
                    {"hold_status": "Select a valid configured hold category."}
                )

            previous_status = None
            if self.pk:
                previous_status = (
                    SemesterResult.objects.filter(pk=self.pk)
                    .values_list("hold_status", flat=True)
                    .first()
                )
            if not category.is_active and previous_status != self.hold_status:
                raise ValidationError(
                    {"hold_status": "Inactive hold categories cannot be newly assigned."}
                )

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

    def get_hold_status_display(self) -> str:
        if (self.hold_status or self.HOLD_NONE) == self.HOLD_NONE:
            return "None"
        return (
            HoldCategory.objects.filter(code=self.hold_status)
            .values_list("name", flat=True)
            .first()
            or self.hold_status
        )

    def __str__(self):
        return f"{self.enrollment.roll_no} | Sem {self.batch.semester_number}"


class ProtectedNotificationQuerySet(models.QuerySet):
    def delete(self):
        raise ValidationError(
            "Result notification history is permanent and cannot be deleted."
        )


class ResultNotification(models.Model):
    """A Full or Clearance notification for one ResultBatch."""

    class NotificationType(models.TextChoices):
        FULL = "full", "Full Notification"
        CLEARANCE = "clearance", "Clearance Notification"

    batch = models.ForeignKey(
        ResultBatch, on_delete=models.PROTECT, related_name="notifications"
    )
    notification_type = models.CharField(
        max_length=16,
        choices=NotificationType.choices,
        default=NotificationType.FULL,
    )

    notification_no = models.CharField(max_length=100, unique=True)
    notification_date = models.DateField()

    # Snapshot of the permanent batch declaration date.
    declaration_date = models.DateField()

    remarks = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ProtectedNotificationQuerySet.as_manager()

    class Meta:
        ordering = ["notification_date", "created_at", "id"]
        indexes = [
            models.Index(
                fields=["batch", "notification_type"],
                name="result_notif_batch_type_idx",
            )
        ]

    def clean(self):
        super().clean()
        if self.batch_id and self.notification_type == self.NotificationType.CLEARANCE:
            official_date = self.batch.official_result_declaration_date
            if official_date and self.declaration_date != official_date:
                raise ValidationError(
                    {"declaration_date": "Clearance notifications must retain the official declaration date."}
                )

    def delete(self, *args, **kwargs):
        raise ValidationError(
            "Result notification history is permanent and cannot be deleted."
        )

    def __str__(self) -> str:
        return f"{self.batch} | {self.notification_no} | {self.get_notification_type_display()}"


class ResultNotificationItem(models.Model):
    """One student row included in a ResultNotification."""

    notification = models.ForeignKey(
        ResultNotification, on_delete=models.CASCADE, related_name="items"
    )
    semester_result = models.ForeignKey(
        SemesterResult, on_delete=models.PROTECT, related_name="notification_items"
    )

    hold_status_snapshot = models.CharField(
        max_length=32,
        default=SemesterResult.HOLD_NONE,
    )
    hold_label_snapshot = models.CharField(max_length=100, blank=True)

    class Meta:
        unique_together = ("notification", "semester_result")

    def __str__(self) -> str:
        return f"{self.notification_id} | {self.semester_result_id}"
