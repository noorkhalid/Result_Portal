from django.db import models


class Department(models.Model):
    """A simple organizational unit (currently only one)."""

    name = models.CharField(max_length=255, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


def get_default_department() -> "Department":
    """Return the first department, creating the default one if missing.

    This is used as a safe fallback so existing forms/views that don't
    expose a department field keep working.
    """
    default_name = "Falcon Educational Complex, Tank"
    obj, _ = Department.objects.get_or_create(name=default_name)
    return obj


class Program(models.Model):
    """
    Example:
    - B.Ed (1.5 Years)
    - AD (2 Years)
    - BS (4 Years)
    """

    DURATION_CHOICES = [
        (3, "1.5 Years (3 Semesters)"),
        (4, "2 Years (4 Semesters)"),
        (5, "2.5 Years (5 Semesters)"),
        (6, "3 Years (6 Semesters)"),
        (8, "4 Years (8 Semesters)"),
        (10, "5 Years (10 Semesters)"),
    ]

    name = models.CharField(max_length=200)
    total_semesters = models.PositiveSmallIntegerField(choices=DURATION_CHOICES)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]
        unique_together = ("name", "total_semesters")

    def __str__(self):
        return f"{self.name} ({self.total_semesters} semesters)"


class ProgramOffering(models.Model):
    """Which department offers which program.

    This model separates *availability* (department context) from *curriculum*
    (Curriculum-by-Session). Program offerings remain department-specific.
    """

    department = models.ForeignKey(
        Department,
        on_delete=models.PROTECT,
        related_name="program_offerings",
    )
    program = models.ForeignKey(
        Program,
        on_delete=models.CASCADE,
        related_name="offerings",
    )
    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("department", "program")
        ordering = ["department__name", "program__name"]

    def __str__(self):
        return f"{self.department.name} → {self.program.name}"


class Session(models.Model):
    """
    Example: 2023
    Actual printed session range depends on Program duration (auto-calculated).
    """

    start_year = models.PositiveSmallIntegerField(unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-start_year"]

    def __str__(self):
        return str(self.start_year)

    def display_for_program(self, program) -> str:
        """
        Returns something like '2023-2025' depending on program duration.
        We assume 2 semesters per year.
        """
        total_semesters = int(program.total_semesters)
        years = (total_semesters + 1) // 2   # 3->2, 4->2, 5->3, 6->3, 8->4, 10->5
        end_year = self.start_year + years
        return f"{self.start_year}-{end_year}"


class Course(models.Model):
    # Courses remain global (not attached to a department)
    code = models.CharField(max_length=30, unique=True)
    title = models.CharField(max_length=255)
    credit_hours = models.DecimalField(max_digits=4, decimal_places=1)

    def __str__(self):
        return f"{self.code or 'NO-CODE'} - {self.title} ({self.credit_hours} CH)"


# -----------------------------
# Curriculum-by-Session (v2)
# -----------------------------


class Curriculum(models.Model):
    """A curriculum version for a specific Program + Session.

    This allows curriculum changes over time (per session) without breaking old transcripts.
    """

    program = models.ForeignKey(Program, on_delete=models.CASCADE, related_name="curricula")
    session = models.ForeignKey(Session, on_delete=models.CASCADE, related_name="curricula")

    # Snapshot of total semesters for this curriculum version
    total_semesters = models.PositiveSmallIntegerField()

    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("program", "session")
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.program.name} | {self.session.start_year} | Curriculum"


class CurriculumCourse(models.Model):
    """Which course is taught in which semester of a *curriculum version*."""

    curriculum = models.ForeignKey(
        Curriculum,
        on_delete=models.CASCADE,
        related_name="curriculum_courses",
    )
    semester_number = models.PositiveSmallIntegerField()
    course = models.ForeignKey(Course, on_delete=models.CASCADE)

    # Optional overrides. If blank, use Course.credit_hours.
    credit_hours_override = models.DecimalField(
        max_digits=4,
        decimal_places=1,
        null=True,
        blank=True,
    )

    class Meta:
        unique_together = ("curriculum", "semester_number", "course")
        ordering = ["semester_number", "course__code"]

    def __str__(self):
        return f"{self.curriculum} | Sem {self.semester_number} | {self.course.code}"
