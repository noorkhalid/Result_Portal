from django.db import models


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
    code = models.CharField(max_length=30, unique=True)
    title = models.CharField(max_length=255, unique=True)
    credit_hours = models.DecimalField(max_digits=4, decimal_places=1)

    def __str__(self):
        return f"{self.code or 'NO-CODE'} - {self.title} ({self.credit_hours} CH)"



class ProgramCourse(models.Model):
    """
    Which course is taught in which semester of a program
    """

    program = models.ForeignKey(Program, on_delete=models.CASCADE)
    semester_number = models.PositiveSmallIntegerField()
    course = models.ForeignKey(Course, on_delete=models.CASCADE)

    class Meta:
        unique_together = ("program", "semester_number", "course")
        ordering = ["semester_number"]

    def __str__(self):
        return f"{self.program.name} | Sem {self.semester_number} | {self.course.title}"
