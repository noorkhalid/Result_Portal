from django import forms

from academics.models import Department, Program, ProgramCourse, Session, Semester
from results.models import GradeScale, ResultBatch
from students.models import Enrollment, Student


class SessionForm(forms.ModelForm):
    class Meta:
        model = Session
        fields = ["start_year", "is_active"]
        widgets = {
            "start_year": forms.NumberInput(attrs={"class": "form-control"}),
            "is_active": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }


class SemesterForm(forms.ModelForm):
    class Meta:
        model = Semester
        fields = ["program", "session", "number"]
        widgets = {
            "program": forms.Select(attrs={"class": "form-select"}),
            "session": forms.Select(attrs={"class": "form-select"}),
            "number": forms.NumberInput(attrs={"class": "form-control"}),
        }


class ProgramCourseForm(forms.ModelForm):
    class Meta:
        model = ProgramCourse
        fields = ["department", "program", "semester_number", "course"]
        widgets = {
            "department": forms.Select(attrs={"class": "form-select"}),
            "program": forms.Select(attrs={"class": "form-select"}),
            "semester_number": forms.NumberInput(attrs={"class": "form-control"}),
            "course": forms.Select(attrs={"class": "form-select"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # If department is known (from POST/instance/initial), filter program queryset
        dept_id = None
        if self.is_bound:
            dept_id = self.data.get("department")
        elif self.instance and getattr(self.instance, "department_id", None):
            dept_id = self.instance.department_id
        elif self.initial.get("department"):
            dept_id = self.initial.get("department")

        if dept_id:
            self.fields["program"].queryset = Program.objects.filter(department_id=dept_id).order_by("name")
        else:
            self.fields["program"].queryset = Program.objects.all().order_by("name")

        self.fields["department"].queryset = Department.objects.all().order_by("name")

    def clean(self):
        cleaned = super().clean()
        dept = cleaned.get("department")
        program = cleaned.get("program")
        if dept and program and program.department_id != dept.id:
            self.add_error("program", "Selected program does not belong to selected department.")
        return cleaned


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
            self.fields["program"].queryset = Program.objects.filter(department_id=dept_id).order_by("name")
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
        if dept and program and program.department_id != dept.id:
            self.add_error("program", "Selected program does not belong to selected department.")
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
            "program",
            "session",
            "semester_number",
            "result_type",
            "notification_no",
            "notification_date",
            "is_locked",
        ]
        widgets = {
            "program": forms.Select(attrs={"class": "form-select"}),
            "session": forms.Select(attrs={"class": "form-select"}),
            "semester_number": forms.NumberInput(attrs={"class": "form-control"}),
            "result_type": forms.Select(attrs={"class": "form-select"}),
            "notification_no": forms.TextInput(attrs={"class": "form-control"}),
            "notification_date": forms.DateInput(attrs={"class": "form-control", "type": "date"}),
            "is_locked": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
