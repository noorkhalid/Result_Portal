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

    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="programs")
    name = models.CharField(max_length=200)
    total_semesters = models.PositiveSmallIntegerField(choices=DURATION_CHOICES)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def save(self, *args, **kwargs):
        if not self.department_id:
            self.department = get_default_department()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.name} ({self.total_semesters} semesters)"


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


class Semester(models.Model):
    program = models.ForeignKey(Program, on_delete=models.CASCADE)
    session = models.ForeignKey(Session, on_delete=models.CASCADE)
    number = models.PositiveSmallIntegerField()

    class Meta:
        unique_together = ("program", "session", "number")
        ordering = ["number"]

    def __str__(self):
        return f"{self.program.name} | {self.session.start_year} | Semester {self.number}"


class Course(models.Model):
    # Courses remain global (not attached to a department)
    code = models.CharField(max_length=30, unique=True)
    title = models.CharField(max_length=255)
    credit_hours = models.DecimalField(max_digits=4, decimal_places=1)

    def __str__(self):
        return f"{self.code or 'NO-CODE'} - {self.title} ({self.credit_hours} CH)"


class ProgramCourse(models.Model):
    """Which course is taught in which semester of a program."""

    department = models.ForeignKey(Department, on_delete=models.PROTECT, related_name="program_courses")
    program = models.ForeignKey(Program, on_delete=models.CASCADE)
    semester_number = models.PositiveSmallIntegerField()
    course = models.ForeignKey(Course, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("program", "semester_number", "course")
        ordering = ["semester_number"]

    def save(self, *args, **kwargs):
        if not self.department_id:
            # Keep in sync with the program's department
            if self.program_id and getattr(self.program, "department_id", None):
                self.department_id = self.program.department_id
            else:
                self.department = get_default_department()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.program.name} | Sem {self.semester_number} | {self.course.title}"
