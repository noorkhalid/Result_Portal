from datetime import date

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import RequestFactory, TestCase
from django.urls import reverse

from academics.models import Curriculum, Department, Program, ProgramOffering, Session
from results.models import ExamType, ResultBatch, ResultNotification, SemesterResult
from results.notification_services import (
    create_result_notification,
    eligible_clearance_results,
)
from students.models import Enrollment, Student


class ResultNotificationFoundationTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="admin",
            email="admin@example.com",
            password="test-pass-123",
        )
        self.department = Department.objects.create(name="Test Department")
        self.program = Program.objects.create(
            name="BS Test",
            total_semesters=4,
            semester_start=1,
        )
        ProgramOffering.objects.create(
            department=self.department,
            program=self.program,
        )
        self.session = Session.objects.create(start_year=2025)
        self.curriculum = Curriculum.objects.create(
            program=self.program,
            session=self.session,
            total_semesters=4,
            semester_start=1,
        )
        self.exam_type = ExamType.objects.create(
            code="regular-test",
            name="Regular Test",
            sort_order=1,
        )
        self.batch = ResultBatch.objects.create(
            department=self.department,
            program=self.program,
            session=self.session,
            curriculum=self.curriculum,
            semester_number=4,
            exam_type=self.exam_type,
        )

        self.results = []
        hold_statuses = [
            SemesterResult.HOLD_DUES,
            SemesterResult.HOLD_DOCUMENTS,
            SemesterResult.HOLD_NONE,
        ]
        for index, hold_status in enumerate(hold_statuses, start=1):
            student = Student.objects.create(
                department=self.department,
                name=f"Student {index}",
                father_name=f"Father {index}",
                registration_no=f"REG-{index}",
            )
            enrollment = Enrollment.objects.create(
                department=self.department,
                student=student,
                program=self.program,
                session=self.session,
                curriculum=self.curriculum,
                roll_no=f"ROLL-{index}",
            )
            self.results.append(
                SemesterResult.objects.create(
                    batch=self.batch,
                    enrollment=enrollment,
                    gpa="3.00",
                    cgpa="3.00",
                    hold_status=hold_status,
                )
            )

    def create_full(self, number="NOT-001", notification_date=date(2026, 8, 1)):
        return create_result_notification(
            batch=self.batch,
            notification_type=ResultNotification.NotificationType.FULL,
            notification_no=number,
            notification_date=notification_date,
        )

    def test_full_notification_includes_entire_batch_and_snapshots_holds(self):
        notification = self.create_full()

        self.assertEqual(notification.items.count(), 3)
        snapshots = {
            item.semester_result_id: (
                item.hold_status_snapshot,
                item.hold_label_snapshot,
            )
            for item in notification.items.all()
        }
        self.assertEqual(
            snapshots[self.results[0].id],
            (SemesterResult.HOLD_DUES, "RL Dues"),
        )
        self.assertEqual(
            snapshots[self.results[1].id],
            (SemesterResult.HOLD_DOCUMENTS, "RL Documents"),
        )
        self.assertEqual(
            snapshots[self.results[2].id],
            (SemesterResult.HOLD_NONE, ""),
        )

        self.batch.refresh_from_db()
        self.assertEqual(
            self.batch.official_result_declaration_date,
            date(2026, 8, 1),
        )
        self.assertEqual(notification.declaration_date, date(2026, 8, 1))

    def test_second_full_notification_is_blocked(self):
        self.create_full()

        with self.assertRaisesMessage(
            ValidationError,
            "A Full Result Notification already exists for this batch.",
        ):
            self.create_full(number="NOT-002", notification_date=date(2026, 8, 2))

    def test_duplicate_notification_number_is_blocked(self):
        self.create_full(number="NOT-001")

        other_batch = ResultBatch.objects.create(
            department=self.department,
            program=self.program,
            session=self.session,
            curriculum=self.curriculum,
            semester_number=1,
            exam_type=self.exam_type,
        )
        with self.assertRaisesMessage(
            ValidationError,
            'Notification number "NOT-001" is already assigned.',
        ):
            create_result_notification(
                batch=other_batch,
                notification_type=ResultNotification.NotificationType.FULL,
                notification_no="not-001",
                notification_date=date(2026, 8, 2),
            )

    def test_clearance_requires_full_notification(self):
        with self.assertRaisesMessage(
            ValidationError,
            "Create the Full Result Notification before a Clearance Notification.",
        ):
            create_result_notification(
                batch=self.batch,
                notification_type=ResultNotification.NotificationType.CLEARANCE,
                notification_no="CLR-001",
                notification_date=date(2026, 8, 2),
                selected_semester_result_ids=[self.results[0].id],
            )

    def test_clearance_uses_selection_and_never_repeats_cleared_student(self):
        self.create_full()

        first_withheld = self.results[0]
        second_withheld = self.results[1]
        first_withheld.hold_status = SemesterResult.HOLD_NONE
        first_withheld.save(update_fields=["hold_status"])
        second_withheld.hold_status = SemesterResult.HOLD_NONE
        second_withheld.save(update_fields=["hold_status"])

        eligible_before = list(
            eligible_clearance_results(self.batch).values_list("id", flat=True)
        )
        self.assertEqual(
            set(eligible_before),
            {first_withheld.id, second_withheld.id},
        )

        clearance = create_result_notification(
            batch=self.batch,
            notification_type=ResultNotification.NotificationType.CLEARANCE,
            notification_no="CLR-001",
            notification_date=date(2026, 8, 10),
            selected_semester_result_ids=[first_withheld.id],
        )

        self.assertEqual(
            list(clearance.items.values_list("semester_result_id", flat=True)),
            [first_withheld.id],
        )
        clearance_item = clearance.items.get()
        self.assertEqual(clearance_item.hold_status_snapshot, SemesterResult.HOLD_NONE)
        self.assertEqual(clearance.declaration_date, date(2026, 8, 1))

        eligible_after = list(
            eligible_clearance_results(self.batch).values_list("id", flat=True)
        )
        self.assertEqual(eligible_after, [second_withheld.id])

        with self.assertRaisesMessage(
            ValidationError,
            "One or more selected students are no longer eligible for clearance.",
        ):
            create_result_notification(
                batch=self.batch,
                notification_type=ResultNotification.NotificationType.CLEARANCE,
                notification_no="CLR-002",
                notification_date=date(2026, 8, 11),
                selected_semester_result_ids=[first_withheld.id],
            )

    def test_official_declaration_date_cannot_be_changed(self):
        self.create_full()
        self.batch.refresh_from_db()
        self.batch.official_result_declaration_date = date(2026, 8, 5)

        with self.assertRaisesMessage(
            ValidationError,
            "The official result declaration date cannot be changed once set.",
        ):
            self.batch.save()

    def test_notification_page_shows_bulk_clearance_controls(self):
        self.create_full()
        held_result = self.results[0]
        held_result.hold_status = SemesterResult.HOLD_NONE
        held_result.save(update_fields=["hold_status"])

        from dashboards.views.result_batch_views import batch_notifications

        request = RequestFactory().get(
            reverse("admin_batch_notifications", args=[self.batch.id])
        )
        request.user = self.user
        request.session = {}
        response = batch_notifications(request, self.batch.id)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Select All")
        self.assertContains(response, "Deselect All")
        self.assertContains(response, held_result.enrollment.student.name)
