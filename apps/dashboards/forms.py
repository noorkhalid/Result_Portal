from django import forms

from academics.models import Department, Program, ProgramOffering, Session
from results.models import ExamType, GradeScale, ResultBatch
from students.models import Enrollment, Student


class SessionForm(forms.ModelForm):
    class Meta:
        model = Session
        fields = ["start_year", "is_active"]
        widgets = {
            "start_year": forms.NumberInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class ProgramOfferingForm(forms.ModelForm):
    class Meta:
        model = ProgramOffering
        fields = ["department", "program", "is_active"]
        widgets = {
            "department": forms.Select(attrs={"class": "form-select"}),
            "program": forms.Select(attrs={"class": "form-select"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["department"].queryset = Department.objects.all().order_by("name")
        # Keep program list ordered, global for now.
        self.fields["program"].queryset = Program.objects.all().order_by("name")


class StudentForm(forms.ModelForm):
    class Meta:
        model = Student
        fields = ["department", "name", "father_name", "registration_no", "is_active"]
        widgets = {
            "department": forms.Select(attrs={"class": "form-select"}),
            "name": forms.TextInput(attrs={"class": "form-control"}),
            "father_name": forms.TextInput(attrs={"class": "form-control"}),
            "registration_no": forms.TextInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["department"].queryset = Department.objects.all().order_by("name")


class EnrollmentForm(forms.ModelForm):
    class Meta:
        model = Enrollment
        fields = ["department", "student", "program", "session", "roll_no", "is_active"]
        widgets = {
            "department": forms.Select(attrs={"class": "form-select"}),
            "student": forms.Select(attrs={"class": "form-select"}),
            "program": forms.Select(attrs={"class": "form-select"}),
            "session": forms.Select(attrs={"class": "form-select"}),
            "roll_no": forms.TextInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        self.fields["department"].queryset = Department.objects.all().order_by("name")

        dept_id = None
        if self.is_bound:
            dept_id = self.data.get("department")
        elif self.instance and getattr(self.instance, "department_id", None):
            dept_id = self.instance.department_id
        elif self.initial.get("department"):
            dept_id = self.initial.get("department")

        if dept_id:
            self.fields["student"].queryset = Student.objects.filter(department_id=dept_id).order_by("name")
            self.fields["program"].queryset = (
                Program.objects.filter(offerings__department_id=dept_id, offerings__is_active=True)
                .distinct()
                .order_by("name")
            )
        else:
            self.fields["student"].queryset = Student.objects.all().order_by("name")
            self.fields["program"].queryset = Program.objects.all().order_by("name")

    def clean(self):
        cleaned = super().clean()
        dept = cleaned.get("department")
        student = cleaned.get("student")
        program = cleaned.get("program")
        if dept and student and student.department_id != dept.id:
            self.add_error("student", "Selected student does not belong to selected department.")
        if dept and program:
            ok = ProgramOffering.objects.filter(
                department_id=dept.id, program_id=program.id, is_active=True
            ).exists()
            if not ok:
                self.add_error("program", "Selected program is not offered in selected department.")
        return cleaned


class GradeScaleForm(forms.ModelForm):
    class Meta:
        model = GradeScale
        fields = [
            "min_percentage",
            "max_percentage",
            "letter_grade",
            "grade_point",
            "remarks",
            "is_fail",
        ]
        widgets = {
            "min_percentage": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "max_percentage": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "letter_grade": forms.TextInput(attrs={"class": "form-control"}),
            "grade_point": forms.NumberInput(attrs={"class": "form-control", "step": "0.01"}),
            "remarks": forms.TextInput(attrs={"class": "form-control"}),
            "is_fail": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class ResultBatchForm(forms.ModelForm):
    class Meta:
        model = ResultBatch
        fields = [
            "department",
            "program",
            "session",
            "semester_number",
            "exam_type",
            "is_locked",
        ]
        widgets = {
            "department": forms.Select(attrs={"class": "form-select"}),
            "program": forms.Select(attrs={"class": "form-select"}),
            "session": forms.Select(attrs={"class": "form-select"}),
            "semester_number": forms.NumberInput(attrs={"class": "form-control"}),
            "exam_type": forms.Select(attrs={"class": "form-select"}),
            "is_locked": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Dependent dropdowns: Department -> Program
        self.fields["department"].queryset = Department.objects.all().order_by("name")

        dept_id = None
        if self.is_bound:
            dept_id = self.data.get("department")
        elif self.instance and getattr(self.instance, "department_id", None):
            dept_id = self.instance.department_id
        elif self.initial.get("department"):
            dept_id = self.initial.get("department")

        if dept_id:
            self.fields["program"].queryset = (
                Program.objects.filter(offerings__department_id=dept_id, offerings__is_active=True)
                .distinct()
                .order_by("name")
            )
        else:
            self.fields["program"].queryset = Program.objects.all().order_by("name")

        self.fields["exam_type"].queryset = ExamType.objects.filter(is_active=True).order_by(
            "sort_order", "name"
        )

    def clean(self):
        cleaned = super().clean()
        dept = cleaned.get("department")
        program = cleaned.get("program")
        semester_number = cleaned.get("semester_number")
        if dept and program:
            ok = ProgramOffering.objects.filter(
                department_id=dept.id, program_id=program.id, is_active=True
            ).exists()
            if not ok:
                self.add_error("program", "Selected program is not offered in selected department.")

        # Semester number validation: respect program semester span (e.g., BS 2 Years starts at semester 5).
        if program and semester_number is not None:
            try:
                sem_int = int(semester_number)
            except Exception:
                sem_int = None

            if sem_int is not None:
                sem_start = int(getattr(program, "semester_start", 1) or 1)
                sem_end = int(getattr(program, "semester_end", 0) or 0)
                if sem_end and (sem_int < sem_start or sem_int > sem_end):
                    self.add_error(
                        "semester_number",
                        f"Semester must be between {sem_start} and {sem_end} for the selected program.",
                    )
        return cleaned
