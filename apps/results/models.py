from django.db import models
from academics.models import Program, Session, Course
from students.models import Enrollment


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
        return f"{self.min_percentage}-{self.max_percentage}: {self.letter_grade} ({self.grade_point})"


class ResultBatch(models.Model):
    """
    A result event for a program+session+semester (Regular/Repeat/Improved).
    """
    RESULT_TYPES = [
        ("regular", "Regular"),
        ("repeat", "Repeat"),
        ("improved", "Improved"),
    ]

    program = models.ForeignKey(Program, on_delete=models.PROTECT)
    session = models.ForeignKey(Session, on_delete=models.PROTECT)
    semester_number = models.PositiveSmallIntegerField()
    result_type = models.CharField(max_length=20, choices=RESULT_TYPES, default="regular")

    notification_no = models.CharField(max_length=100, blank=True)
    notification_date = models.DateField(null=True, blank=True)

    is_locked = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("program", "session", "semester_number", "result_type")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.program} | {self.session.start_year} | Sem {self.semester_number} | {self.result_type}"


class CourseResult(models.Model):
    """
    Marks per course per student for a specific batch.
    """
    batch = models.ForeignKey(ResultBatch, on_delete=models.CASCADE, related_name="course_results")
    enrollment = models.ForeignKey(Enrollment, on_delete=models.PROTECT, related_name="course_results")
    course = models.ForeignKey(Course, on_delete=models.PROTECT)

    marks_obtained = models.DecimalField(max_digits=6, decimal_places=2)
    max_marks = models.DecimalField(max_digits=6, decimal_places=2, default=100)

    # calculated fields
    percentage = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    letter_grade = models.CharField(max_length=5, blank=True)
    grade_point = models.DecimalField(max_digits=4, decimal_places=2, default=0)

    class Meta:
        unique_together = ("batch", "enrollment", "course")

    def __str__(self):
        return f"{self.enrollment.roll_no} | {self.course.code} | {self.course.title}"


class SemesterResult(models.Model):
    """
    One row per student per semester batch.
    """
    batch = models.ForeignKey(ResultBatch, on_delete=models.CASCADE, related_name="semester_results")
    enrollment = models.ForeignKey(Enrollment, on_delete=models.PROTECT, related_name="semester_results")

    # NEW (very useful for prints)
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
