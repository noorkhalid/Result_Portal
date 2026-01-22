from django.db import models
from academics.models import Program, Session


class Student(models.Model):
    name = models.CharField(max_length=200)
    father_name = models.CharField(max_length=200)
    registration_no = models.CharField(max_length=50, unique=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return f"{self.name} ({self.registration_no})"


class Enrollment(models.Model):
    """
    A student enrolled in a Program under a Session (start year).
    Roll number can vary by program/session.
    """

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name="enrollments")
    program = models.ForeignKey(Program, on_delete=models.PROTECT)
    session = models.ForeignKey(Session, on_delete=models.PROTECT)
    roll_no = models.CharField(max_length=50)

    is_active = models.BooleanField(default=True)

    class Meta:
        unique_together = ("program", "session", "roll_no")
        ordering = ["program", "roll_no"]

    def __str__(self):
        return f"{self.program.name} | {self.session.start_year} | {self.roll_no}"
