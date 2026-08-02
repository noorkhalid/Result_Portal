from datetime import date

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
from django.db.models.deletion import ProtectedError
from django.test import RequestFactory, TestCase
from django.urls import reverse

from academics.models import (
    Course,
    Curriculum,
    CurriculumCourse,
    Department,
    Program,
    ProgramOffering,
    Session,
)
from results.models import (
    CourseResult,
    ExamType,
    HoldCategory,
    ResultBatch,
    ResultNotification,
    SemesterResult,
)
from results.dmc_services import evaluate_dmc_eligibility
from results.notification_services import (
    create_result_notification,
    eligible_clearance_results,
    suggest_next_notification_number,
)
from results.transcript_services import evaluate_transcript_eligibility
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

    def create_full(
        self,
        number="0001-2026/Results/Exam/GU",
        notification_date=date(2026, 8, 1),
    ):
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
            self.create_full(number="0002-2026/Results/Exam/GU", notification_date=date(2026, 8, 2))

    def test_duplicate_notification_number_is_blocked(self):
        self.create_full(number="0001-2026/Results/Exam/GU")

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
            'Notification number "0001-2026/Results/Exam/GU" is already assigned.',
        ):
            create_result_notification(
                batch=other_batch,
                notification_type=ResultNotification.NotificationType.FULL,
                notification_no="0001-2026/Results/Exam/GU",
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
                notification_no="0001-2026/Results/Exam/GU",
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
            notification_no="0002-2026/Results/Exam/GU",
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
                notification_no="0003-2026/Results/Exam/GU",
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

    def test_number_suggestion_restarts_each_year_and_reuses_gap(self):
        ResultNotification.objects.create(
            batch=self.batch,
            notification_type=ResultNotification.NotificationType.FULL,
            notification_no="0001-2026/Results/Exam/GU",
            notification_date=date(2026, 1, 10),
            declaration_date=date(2026, 1, 10),
        )
        ResultNotification.objects.create(
            batch=self.batch,
            notification_type=ResultNotification.NotificationType.CLEARANCE,
            notification_no="0003-2026/Results/Exam/GU",
            notification_date=date(2026, 2, 10),
            declaration_date=date(2026, 1, 10),
        )
        ResultNotification.objects.create(
            batch=self.batch,
            notification_type=ResultNotification.NotificationType.CLEARANCE,
            notification_no="FECS (43/08)/2025",
            notification_date=date(2025, 8, 1),
            declaration_date=date(2025, 8, 1),
        )

        self.assertEqual(
            suggest_next_notification_number(date(2026, 8, 1)),
            "0002-2026/Results/Exam/GU",
        )
        self.assertEqual(
            suggest_next_notification_number(date(2027, 1, 1)),
            "0001-2027/Results/Exam/GU",
        )

    def test_notification_number_year_must_match_notification_date(self):
        with self.assertRaisesMessage(
            ValidationError,
            "The notification number year must match the Notification Date year.",
        ):
            self.create_full(
                number="0001-2027/Results/Exam/GU",
                notification_date=date(2026, 8, 1),
            )

    def test_new_notification_number_must_use_official_format(self):
        with self.assertRaisesMessage(
            ValidationError,
            'Use the notification number format "0001-YYYY/Results/Exam/GU".',
        ):
            self.create_full(number="FECS (43/08)/2026")

    def test_notification_history_cannot_be_deleted(self):
        notification = self.create_full()

        with self.assertRaisesMessage(
            ValidationError,
            "Result notification history is permanent and cannot be deleted.",
        ):
            notification.delete()

        with self.assertRaisesMessage(
            ValidationError,
            "Result notification history is permanent and cannot be deleted.",
        ):
            ResultNotification.objects.filter(pk=notification.pk).delete()

        with self.assertRaises(ProtectedError):
            notification.items.first().semester_result.delete()

        with self.assertRaises(ProtectedError):
            self.batch.delete()

        self.assertTrue(ResultNotification.objects.filter(pk=notification.pk).exists())

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
        self.assertContains(response, "0002-2026/Results/Exam/GU")

    def _hold_form_data(self, overrides=None):
        overrides = overrides or {}
        data = {}
        for semester_result in self.results:
            data[f"hold_status_{semester_result.id}"] = overrides.get(
                semester_result.id, semester_result.hold_status
            )
            data[f"hold_note_{semester_result.id}"] = semester_result.hold_note
        return data

    def test_seeded_and_custom_hold_categories_are_supported(self):
        self.assertTrue(
            HoldCategory.objects.filter(code="dues", name="RL Dues").exists()
        )
        self.assertTrue(
            HoldCategory.objects.filter(
                code="documents", name="RL Documents"
            ).exists()
        )

        custom = HoldCategory.objects.create(
            code="verification",
            name="RL Verification",
            sort_order=30,
        )
        held_result = self.results[2]
        held_result.hold_status = custom.code
        held_result.save(update_fields=["hold_status"])

        notification = self.create_full()
        item = notification.items.get(semester_result=held_result)
        self.assertEqual(item.hold_status_snapshot, "verification")
        self.assertEqual(item.hold_label_snapshot, "RL Verification")

    def test_used_hold_category_cannot_be_deleted_or_recoded(self):
        category = HoldCategory.objects.get(code="documents")

        with self.assertRaisesMessage(
            ValidationError,
            "This hold category is already used in results or notification history.",
        ):
            category.delete()

        category.code = "documents-updated"
        with self.assertRaisesMessage(
            ValidationError,
            "The code cannot be changed because this category is already in use.",
        ):
            category.save()

        self.assertTrue(HoldCategory.objects.filter(code="documents").exists())

    def test_clearing_hold_records_user_and_time(self):
        self.client.force_login(self.user)
        held_result = self.results[0]
        response = self.client.post(
            reverse("admin_batch_students_holds", args=[self.batch.id]),
            data=self._hold_form_data(
                {held_result.id: SemesterResult.HOLD_NONE}
            ),
        )

        self.assertEqual(response.status_code, 302)
        held_result.refresh_from_db()
        self.assertEqual(held_result.hold_status, SemesterResult.HOLD_NONE)
        self.assertIsNotNone(held_result.hold_cleared_at)
        self.assertEqual(held_result.hold_cleared_by, self.user)

    def test_inactive_hold_category_cannot_be_newly_assigned(self):
        inactive = HoldCategory.objects.create(
            code="legacy-check",
            name="RL Legacy Check",
            is_active=False,
        )
        clear_result = self.results[2]

        clear_result.hold_status = inactive.code
        with self.assertRaisesMessage(
            ValidationError,
            "Inactive hold categories cannot be newly assigned.",
        ):
            clear_result.save(update_fields=["hold_status"])
        clear_result.hold_status = SemesterResult.HOLD_NONE

        self.client.force_login(self.user)

        response = self.client.post(
            reverse("admin_batch_students_holds", args=[self.batch.id]),
            data=self._hold_form_data({clear_result.id: inactive.code}),
        )

        self.assertEqual(response.status_code, 302)
        clear_result.refresh_from_db()
        self.assertEqual(clear_result.hold_status, SemesterResult.HOLD_NONE)

    def test_hold_category_setup_is_system_admin_only(self):
        from dashboards.views.hold_category_views import hold_category_list

        request = RequestFactory().get(reverse("admin_hold_category_list"))
        request.user = self.user
        request.session = {}
        response = hold_category_list(request)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Hold Categories")

        assistant = get_user_model().objects.create_user(
            username="assistant",
            password="test-pass-123",
        )
        assistant_group, _ = Group.objects.get_or_create(name="Dealing Assistant")
        assistant.groups.add(assistant_group)
        self.client.force_login(assistant)

        response = self.client.get(reverse("admin_hold_category_list"))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard"))


class TranscriptEligibilityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="transcript-admin",
            email="transcript@example.com",
            password="test-pass-123",
        )
        self.department = Department.objects.create(name="Transcript Department")
        self.program = Program.objects.create(
            name="BS Transcript Test",
            total_semesters=2,
            semester_start=1,
        )
        ProgramOffering.objects.create(
            department=self.department,
            program=self.program,
        )
        self.session = Session.objects.create(start_year=2024)
        self.curriculum = Curriculum.objects.create(
            program=self.program,
            session=self.session,
            total_semesters=2,
            semester_start=1,
        )
        self.regular = ExamType.objects.create(
            code="regular-transcript-test",
            name="Regular Transcript Test",
            sort_order=1,
        )
        self.repeat, _ = ExamType.objects.get_or_create(
            code="repeat",
            defaults={"name": "Repeat", "sort_order": 2},
        )
        self.course_one = Course.objects.create(
            code="TR-101",
            title="Transcript Course One",
            credit_hours="3.0",
        )
        self.course_two = Course.objects.create(
            code="TR-102",
            title="Transcript Course Two",
            credit_hours="3.0",
        )
        CurriculumCourse.objects.create(
            curriculum=self.curriculum,
            semester_number=1,
            course=self.course_one,
        )
        CurriculumCourse.objects.create(
            curriculum=self.curriculum,
            semester_number=2,
            course=self.course_two,
        )
        self.student = Student.objects.create(
            department=self.department,
            name="Transcript Student",
            father_name="Transcript Father",
            registration_no="TRANSCRIPT-REG-1",
        )
        self.enrollment = Enrollment.objects.create(
            department=self.department,
            student=self.student,
            program=self.program,
            session=self.session,
            curriculum=self.curriculum,
            roll_no="TRANSCRIPT-ROLL-1",
        )
        self.batch_one = ResultBatch.objects.create(
            department=self.department,
            program=self.program,
            session=self.session,
            curriculum=self.curriculum,
            semester_number=1,
            exam_type=self.regular,
        )
        self.batch_two = ResultBatch.objects.create(
            department=self.department,
            program=self.program,
            session=self.session,
            curriculum=self.curriculum,
            semester_number=2,
            exam_type=self.regular,
        )
        self.semester_one = SemesterResult.objects.create(
            batch=self.batch_one,
            enrollment=self.enrollment,
            gpa="3.00",
            cgpa="3.00",
        )
        self.semester_two = SemesterResult.objects.create(
            batch=self.batch_two,
            enrollment=self.enrollment,
            gpa="3.00",
            cgpa="3.00",
        )
        self.result_one = CourseResult.objects.create(
            batch=self.batch_one,
            enrollment=self.enrollment,
            course=self.course_one,
            marks_obtained="45.00",
            letter_grade="B",
            grade_point="3.00",
        )
        self.result_two = CourseResult.objects.create(
            batch=self.batch_two,
            enrollment=self.enrollment,
            course=self.course_two,
            marks_obtained="45.00",
            letter_grade="B",
            grade_point="3.00",
        )

    def publish(self, batch, number, selected_ids=None, notification_type="full"):
        return create_result_notification(
            batch=batch,
            notification_type=notification_type,
            notification_no=number,
            notification_date=date(2026, 8, 2),
            selected_semester_result_ids=selected_ids,
        )

    def publish_regular_results(self):
        self.publish(self.batch_one, "0101-2026/Results/Exam/GU")
        self.publish(self.batch_two, "0102-2026/Results/Exam/GU")

    def test_eligible_only_after_all_required_results_are_officially_released(self):
        before = evaluate_transcript_eligibility(self.enrollment)
        self.assertFalse(before.is_eligible)
        self.assertIn("Result not officially released", before.reason)

        self.publish_regular_results()

        after = evaluate_transcript_eligibility(self.enrollment)
        self.assertTrue(after.is_eligible)
        self.assertEqual(after.reasons, ())

    def test_missing_semester_result_is_reported(self):
        self.semester_one.delete()

        status = evaluate_transcript_eligibility(self.enrollment)

        self.assertFalse(status.is_eligible)
        self.assertIn("Missing semester result(s): 1.", status.reason)

    def test_missing_required_course_result_is_reported(self):
        self.result_two.delete()
        self.publish_regular_results()

        status = evaluate_transcript_eligibility(self.enrollment)

        self.assertFalse(status.is_eligible)
        self.assertIn("Missing required course result(s): TR-102.", status.reason)

    def test_active_hold_requires_clearance_notification(self):
        HoldCategory.objects.get_or_create(
            code="documents",
            defaults={"name": "RL Documents", "sort_order": 20},
        )
        self.semester_two.hold_status = SemesterResult.HOLD_DOCUMENTS
        self.semester_two.save(update_fields=["hold_status"])
        self.publish_regular_results()

        held = evaluate_transcript_eligibility(self.enrollment)
        self.assertFalse(held.is_eligible)
        self.assertIn("Active result hold(s)", held.reason)
        self.assertIn("Result not officially released", held.reason)

        self.semester_two.hold_status = SemesterResult.HOLD_NONE
        self.semester_two.save(update_fields=["hold_status"])
        self.publish(
            self.batch_two,
            "0103-2026/Results/Exam/GU",
            selected_ids=[self.semester_two.id],
            notification_type=ResultNotification.NotificationType.CLEARANCE,
        )

        cleared = evaluate_transcript_eligibility(self.enrollment)
        self.assertTrue(cleared.is_eligible)

    def test_later_repeat_pass_clears_an_earlier_failed_course(self):
        self.result_one.letter_grade = "F"
        self.result_one.grade_point = "0.00"
        self.result_one.save(update_fields=["letter_grade", "grade_point"])
        self.publish_regular_results()

        failed = evaluate_transcript_eligibility(self.enrollment)
        self.assertFalse(failed.is_eligible)
        self.assertIn("Uncleared failed course(s): TR-101.", failed.reason)

        repeat_batch = ResultBatch.objects.create(
            department=self.department,
            program=self.program,
            session=self.session,
            curriculum=self.curriculum,
            semester_number=1,
            exam_type=self.repeat,
        )
        repeat_semester = SemesterResult.objects.create(
            batch=repeat_batch,
            enrollment=self.enrollment,
            gpa="3.00",
            cgpa="3.00",
        )
        CourseResult.objects.create(
            batch=repeat_batch,
            enrollment=self.enrollment,
            course=self.course_one,
            marks_obtained="45.00",
            letter_grade="B",
            grade_point="3.00",
        )
        self.publish(repeat_batch, "0103-2026/Results/Exam/GU")

        passed = evaluate_transcript_eligibility(self.enrollment)
        self.assertTrue(passed.is_eligible)
        self.assertTrue(
            repeat_semester.notification_items.filter(
                hold_status_snapshot=SemesterResult.HOLD_NONE
            ).exists()
        )

    def test_direct_single_pdf_url_is_protected_by_eligibility_rule(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("transcript_pdf", args=[self.enrollment.id])
        )

        self.assertEqual(response.status_code, 403)
        self.assertContains(
            response,
            "Result not officially released",
            status_code=403,
        )

    def test_direct_selected_pdf_url_rejects_ineligible_student(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("transcript_batch_pdf", args=[self.batch_two.id]),
            {"enrollments": str(self.enrollment.id)},
        )

        self.assertEqual(response.status_code, 403)
        self.assertContains(
            response,
            "Transcript is not available for the selected student",
            status_code=403,
        )


class DMCEligibilityTests(TestCase):
    def setUp(self):
        self.user = get_user_model().objects.create_superuser(
            username="dmc-admin",
            email="dmc@example.com",
            password="test-pass-123",
        )
        self.department = Department.objects.create(name="DMC Department")
        self.program = Program.objects.create(
            name="BS DMC Test",
            total_semesters=1,
            semester_start=1,
        )
        ProgramOffering.objects.create(
            department=self.department,
            program=self.program,
        )
        self.session = Session.objects.create(start_year=2023)
        self.curriculum = Curriculum.objects.create(
            program=self.program,
            session=self.session,
            total_semesters=1,
            semester_start=1,
        )
        self.regular = ExamType.objects.create(
            code="regular-dmc-test",
            name="Regular DMC Test",
            sort_order=1,
        )
        self.course_one = Course.objects.create(
            code="DMC-101",
            title="DMC Course One",
            credit_hours="3.0",
        )
        self.course_two = Course.objects.create(
            code="DMC-102",
            title="DMC Course Two",
            credit_hours="3.0",
        )
        CurriculumCourse.objects.create(
            curriculum=self.curriculum,
            semester_number=1,
            course=self.course_one,
        )
        CurriculumCourse.objects.create(
            curriculum=self.curriculum,
            semester_number=1,
            course=self.course_two,
        )
        self.batch = ResultBatch.objects.create(
            department=self.department,
            program=self.program,
            session=self.session,
            curriculum=self.curriculum,
            semester_number=1,
            exam_type=self.regular,
        )

        self.results = []
        for index in range(1, 3):
            student = Student.objects.create(
                department=self.department,
                name=f"DMC Student {index}",
                father_name=f"DMC Father {index}",
                registration_no=f"DMC-REG-{index}",
            )
            enrollment = Enrollment.objects.create(
                department=self.department,
                student=student,
                program=self.program,
                session=self.session,
                curriculum=self.curriculum,
                roll_no=f"DMC-ROLL-{index}",
            )
            semester_result = SemesterResult.objects.create(
                batch=self.batch,
                enrollment=enrollment,
                gpa="3.00",
                cgpa="3.00",
            )
            CourseResult.objects.create(
                batch=self.batch,
                enrollment=enrollment,
                course=self.course_one,
                marks_obtained="45.00",
                letter_grade="B",
                grade_point="3.00",
            )
            CourseResult.objects.create(
                batch=self.batch,
                enrollment=enrollment,
                course=self.course_two,
                marks_obtained="45.00",
                letter_grade="B",
                grade_point="3.00",
            )
            self.results.append(semester_result)

    def publish_full(self):
        return create_result_notification(
            batch=self.batch,
            notification_type=ResultNotification.NotificationType.FULL,
            notification_no="0201-2026/Results/Exam/GU",
            notification_date=date(2026, 8, 2),
        )

    def test_dmc_requires_official_release(self):
        before = evaluate_dmc_eligibility(self.results[0])
        self.assertFalse(before.is_eligible)
        self.assertIn("Result has not been officially released", before.reason)

        self.publish_full()

        after = evaluate_dmc_eligibility(self.results[0])
        self.assertTrue(after.is_eligible)

    def test_dmc_requires_all_batch_course_results(self):
        CourseResult.objects.filter(
            batch=self.batch,
            enrollment=self.results[0].enrollment,
            course=self.course_two,
        ).delete()
        self.publish_full()

        status = evaluate_dmc_eligibility(self.results[0])

        self.assertFalse(status.is_eligible)
        self.assertIn("Missing course result(s): DMC-102.", status.reason)

    def test_failed_course_does_not_block_dmc(self):
        failed_course = CourseResult.objects.get(
            batch=self.batch,
            enrollment=self.results[0].enrollment,
            course=self.course_one,
        )
        failed_course.letter_grade = "F"
        failed_course.grade_point = "0.00"
        failed_course.save(update_fields=["letter_grade", "grade_point"])
        self.publish_full()

        status = evaluate_dmc_eligibility(self.results[0])

        self.assertTrue(status.is_eligible)

    def test_held_result_requires_clearance_notification(self):
        held_result = self.results[0]
        held_result.hold_status = SemesterResult.HOLD_DOCUMENTS
        held_result.save(update_fields=["hold_status"])
        self.publish_full()

        held = evaluate_dmc_eligibility(held_result)
        self.assertFalse(held.is_eligible)
        self.assertIn("Active result hold: RL Documents.", held.reason)
        self.assertIn("Result has not been officially released", held.reason)

        held_result.hold_status = SemesterResult.HOLD_NONE
        held_result.save(update_fields=["hold_status"])
        still_unreleased = evaluate_dmc_eligibility(held_result)
        self.assertFalse(still_unreleased.is_eligible)

        create_result_notification(
            batch=self.batch,
            notification_type=ResultNotification.NotificationType.CLEARANCE,
            notification_no="0202-2026/Results/Exam/GU",
            notification_date=date(2026, 8, 3),
            selected_semester_result_ids=[held_result.id],
        )

        cleared = evaluate_dmc_eligibility(held_result)
        self.assertTrue(cleared.is_eligible)

    def test_direct_single_dmc_url_is_protected(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse(
                "dmc_single_pdf",
                args=[self.batch.id, self.results[0].enrollment_id],
            )
        )

        self.assertEqual(response.status_code, 403)
        self.assertContains(
            response,
            "Result has not been officially released",
            status_code=403,
        )

    def test_direct_selected_dmc_url_rejects_ineligible_student(self):
        self.client.force_login(self.user)

        response = self.client.get(
            reverse("dmc_batch_pdf", args=[self.batch.id]),
            {"enrollments": str(self.results[0].enrollment_id)},
        )

        self.assertEqual(response.status_code, 403)
        self.assertContains(
            response,
            "DMC is not available for the selected student",
            status_code=403,
        )

    def test_selected_dmc_page_shows_eligibility_reasons(self):
        held_result = self.results[0]
        held_result.hold_status = SemesterResult.HOLD_DOCUMENTS
        held_result.save(update_fields=["hold_status"])
        self.publish_full()
        from dashboards.views.dmc_views import dmc_selected

        request = RequestFactory().get(
            reverse("admin_dmc_selected", args=[self.batch.id])
        )
        request.user = self.user
        request.session = {}
        response = dmc_selected(request, self.batch.id)

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Eligible")
        self.assertContains(response, "Not Eligible")
        self.assertContains(response, "Active result hold: RL Documents.")
        self.assertContains(response, "Select All Eligible")
