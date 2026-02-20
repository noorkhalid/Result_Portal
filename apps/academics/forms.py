from django import forms
from .models import Course


class CourseForm(forms.ModelForm):
    class Meta:
        model = Course
        fields = ["code", "title", "credit_hours"]

    # Show derived max marks in the form (read-only)
    max_marks_preview = forms.IntegerField(
        label="Max Marks (auto)",
        required=False,
        disabled=True,
        help_text="Automatically calculated as credit_hours × 10.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Populate preview from instance (or from posted credit_hours when available)
        ch = None
        if self.is_bound:
            try:
                ch = float(self.data.get("credit_hours"))
            except Exception:
                ch = None
        if ch is None and self.instance and getattr(self.instance, "credit_hours", None) is not None:
            try:
                ch = float(self.instance.credit_hours)
            except Exception:
                ch = None
        self.fields["max_marks_preview"].initial = int(round(ch * 20)) if ch is not None else 0
