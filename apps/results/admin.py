from decimal import Decimal, ROUND_HALF_UP

from django.contrib import admin
from django.db.models import Sum
from django.urls import reverse
from django.utils.html import format_html

from .models import ResultBatch, CourseResult, SemesterResult, GradeScale


# -------------------------------------------------
# Helpers
# -------------------------------------------------
Q2 = Decimal("0.01")


def q2(x):
    return Decimal(x).quantize(Q2, rounding=ROUND_HALF_UP)


# -------------------------------------------------
# Result Batch
# -------------------------------------------------
@admin.register(ResultBatch)
class ResultBatchAdmin(admin.ModelAdmin):
    list_display = (
        "program",
        "session",
        "semester_number",
        "result_type",
        "is_locked",
        "notification_no",
        "notification_date",
        "created_at",
        "notification_pdf",  # ✅ added
    )
    list_filter = (
        "program",
        "session",
        "semester_number",
        "result_type",
        "is_locked",
    )
    search_fields = ("notification_no",)
    ordering = ("-created_at",)

    def notification_pdf(self, obj):
        """
        Admin list button to open the Result Notification PDF in a new tab.
        Requires URL name: result_notification_pdf with arg: batch_id
        """
        try:
            url = reverse("result_notification_pdf", args=[obj.id])
        except Exception:
            # If URL is not found for any reason, fail safely (no admin crash)
            return "-"

        return format_html(
            '<a class="button" href="{}" target="_blank" rel="noopener">PDF</a>',
            url,
        )

    notification_pdf.short_description = "Notification PDF"


# -------------------------------------------------
# Course Result
# -------------------------------------------------
@admin.register(CourseResult)
class CourseResultAdmin(admin.ModelAdmin):
    list_display = (
        "batch",
        "enrollment",
        "course",
        "marks_obtained",
        "max_marks",
        "percentage",
        "letter_grade",
        "grade_point",
    )
    list_filter = (
        "batch__program",
        "batch__session",
        "batch__semester_number",
        "batch__result_type",
        "course",
    )
    search_fields = (
        "enrollment__roll_no",
        "enrollment__student__registration_no",
        "course__title",
        "course__code",
    )


# -------------------------------------------------
# Semester Result (MAIN FOCUS)
# -------------------------------------------------
@admin.register(SemesterResult)
class SemesterResultAdmin(admin.ModelAdmin):
    list_display = (
        "batch",
        "enrollment",
        "total_obtained",
        "total_marks",
        "percentage",
        "gpa",
        "cgpa",
        "letter_grade",
        "remarks",
    )

    list_filter = (
        "batch__program",
        "batch__session",
        "batch__semester_number",
        "batch__result_type",
    )

    search_fields = (
        "enrollment__roll_no",
        "enrollment__student__registration_no",
    )

    # -----------------------------
    # Computed columns
    # -----------------------------
    def total_obtained(self, obj):
        val = (
            CourseResult.objects.filter(
                batch=obj.batch,
                enrollment=obj.enrollment,
            )
            .aggregate(total=Sum("marks_obtained"))
            .get("total")
        )
        return q2(val or 0)

    total_obtained.short_description = "Total Obtained"

    def total_marks(self, obj):
        val = (
            CourseResult.objects.filter(
                batch=obj.batch,
                enrollment=obj.enrollment,
            )
            .aggregate(total=Sum("max_marks"))
            .get("total")
        )
        return q2(val or 0)

    total_marks.short_description = "Total Marks"

    def percentage(self, obj):
        obtained = self.total_obtained(obj)
        maximum = self.total_marks(obj)
        if maximum > 0:
            return q2((obtained / maximum) * 100)
        return Decimal("0.00")

    percentage.short_description = "Percentage (%)"


# -------------------------------------------------
# Grade Scale
# -------------------------------------------------
@admin.register(GradeScale)
class GradeScaleAdmin(admin.ModelAdmin):
    list_display = (
        "min_percentage",
        "max_percentage",
        "letter_grade",
        "grade_point",
        "remarks",
        "is_fail",
    )
    list_filter = ("is_fail",)
    ordering = ("-min_percentage",)
