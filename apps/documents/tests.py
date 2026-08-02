from datetime import date
from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.core.exceptions import ValidationError
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
from dashboards.views.document_issuance_views import (
    bank_list,
    bank_slip_list,
    document_inventory_list,
    document_issuance_register,
)
from documents.forms import DocumentIssuanceForm
from documents.models import Bank, BankSlip, DocumentInventory, DocumentIssuance
from documents.services import create_document_issuance, next_available_serial
from results.models import CourseResult, ExamType, ResultBatch, ResultNotification, SemesterResult
from results.notification_services import create_result_notification
from results.views import dmc_batch_pdf
from students.models import Enrollment, Student


class DocumentIssuanceTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.admin = user_model.objects.create_superuser(
            username="admin-docs",
            email="admin-docs@example.com",
            password="test-pass-123",
        )
        self.generator = user_model.objects.create_user(
            username="document-generator",
            password="test-pass-123",
        )
        self.controller = user_model.objects.create_user(
            username="controller-docs",
            password="test-pass-123",
        )
        self.assistant = user_model.objects.create_user(
            username="assistant-docs",
            password="test-pass-123",
        )
        for user, group_name in (
            (self.generator, "Document Generator"),
            (self.controller, "Controller"),
            (self.assistant, "Dealing Assistant"),
        ):
            group, _ = Group.objects.get_or_create(name=group_name)
            user.groups.add(group)

        self.department = Department.objects.create(
            name="Document Test Department",
            assigned_assistant=self.assistant,
        )
        self.program = Program.objects.create(
            name="Document Test Program",
            total_semesters=1,
            semester_start=1,
        )
        ProgramOffering.objects.create(
            department=self.department,
            program=self.program,
        )
        self.session = Session.objects.create(start_year=2026)
        self.curriculum = Curriculum.objects.create(
            program=self.program,
            session=self.session,
            total_semesters=1,
            semester_start=1,
        )
        self.course = Course.objects.create(
            code="DOC-101",
            title="Document Test Course",
            credit_hours="3.0",
        )
        CurriculumCourse.objects.create(
            curriculum=self.curriculum,
            semester_number=1,
            course=self.course,
        )
        self.exam_type = ExamType.objects.create(
            code="regular-docs",
            name="Regular Documents",
            sort_order=1,
        )
        self.batch = ResultBatch.objects.create(
            department=self.department,
            program=self.program,
            session=self.session,
            curriculum=self.curriculum,
            semester_number=1,
            exam_type=self.exam_type,
        )

        self.student = Student.objects.create(
            department=self.department,
            name="Document Student",
            father_name="Document Father",
            registration_no="DOC-REG-001",
        )
        self.enrollment = Enrollment.objects.create(
            department=self.department,
            student=self.student,
            program=self.program,
            session=self.session,
            curriculum=self.curriculum,
            roll_no="DOC-ROLL-001",
        )
        self.second_student = Student.objects.create(
            department=self.department,
            name="Second Document Student",
            father_name="Second Father",
            registration_no="DOC-REG-002",
        )
        self.second_enrollment = Enrollment.objects.create(
            department=self.department,
            student=self.second_student,
            program=self.program,
            session=self.session,
            curriculum=self.curriculum,
            roll_no="DOC-ROLL-002",
        )

        for enrollment in (self.enrollment, self.second_enrollment):
            CourseResult.objects.create(
                batch=self.batch,
                enrollment=enrollment,
                course=self.course,
                marks_obtained="50.00",
                percentage="83.33",
                letter_grade="A",
                grade_point="4.00",
            )
        self.semester_result = SemesterResult.objects.create(
            batch=self.batch,
            enrollment=self.enrollment,
            total_obtained="50.00",
            total_max="60.00",
            percentage="83.33",
            gpa="4.00",
            cgpa="4.00",
            letter_grade="A",
            remarks="Excellent",
            hold_status=SemesterResult.HOLD_NONE,
        )
        self.second_semester_result = SemesterResult.objects.create(
            batch=self.batch,
            enrollment=self.second_enrollment,
            total_obtained="50.00",
            total_max="60.00",
            percentage="83.33",
            gpa="4.00",
            cgpa="4.00",
            letter_grade="A",
            remarks="Excellent",
            hold_status=SemesterResult.HOLD_NONE,
        )
        self.notification = create_result_notification(
            batch=self.batch,
            notification_type=ResultNotification.NotificationType.FULL,
            notification_no="9001-2026/Results/Exam/GU",
            notification_date=date(2026, 8, 2),
        )

        self.inventory = DocumentInventory.objects.create(
            start_number=1001,
            bundle_size=500,
            received_date=date(2026, 8, 1),
            created_by=self.controller,
        )
        self.bank = Bank.objects.create(
            name="Test Bank",
            sort_order=1,
            created_by=self.controller,
        )
        self.shared_slip = BankSlip.objects.create(
            bank=self.bank,
            deposit_type=BankSlip.DepositType.CASH_DEPOSIT,
            slip_no="COLLEGE-SLIP-001",
            deposit_date=date(2026, 8, 2),
            total_amount="5000.00",
            depositor_name="Document Test College",
            created_by=self.generator,
        )

    def issue_dmc(self, **overrides):
        data = {
            "document_type": DocumentInventory.DocumentType.DMC,
            "issued_by": self.generator,
            "serial_number": 1001,
            "issue_date": date(2026, 8, 2),
            "payment_slip": self.shared_slip,
            "amount_utilized": "1000.00",
            "recipient_name": self.student.name,
            "semester_result": self.semester_result,
        }
        data.update(overrides)
        return create_document_issuance(**data)

    def issue_transcript(self, **overrides):
        data = {
            "document_type": DocumentInventory.DocumentType.TRANSCRIPT,
            "issued_by": self.generator,
            "serial_number": 1002,
            "issue_date": date(2026, 8, 2),
            "payment_slip": self.shared_slip,
            "amount_utilized": "1500.00",
            "recipient_name": self.student.name,
            "enrollment": self.enrollment,
            "source_batch": self.batch,
        }
        data.update(overrides)
        return create_document_issuance(**data)

    def test_inventory_calculates_end_serial_and_uses_one_common_bundle(self):
        self.assertEqual(self.inventory.start_number, 1001)
        self.assertEqual(self.inventory.bundle_size, 500)
        self.assertEqual(self.inventory.end_number, 1500)
        self.assertEqual(self.inventory.total_count, 500)
        self.assertEqual(next_available_serial(), 1001)

        self.issue_dmc()
        self.assertEqual(next_available_serial(), 1002)
        self.issue_transcript()
        self.inventory.refresh_from_db()
        self.assertEqual(self.inventory.used_count, 2)
        self.assertEqual(self.inventory.available_count, 498)

    def test_overlapping_common_sheet_bundle_is_blocked(self):
        with self.assertRaisesMessage(ValidationError, "overlaps"):
            DocumentInventory.objects.create(
                start_number=1500,
                bundle_size=500,
                created_by=self.controller,
            )

    def test_issue_form_hides_inventory_and_defaults_cash_deposit(self):
        form = DocumentIssuanceForm(
            recipient_name=self.student.name,
            suggested_serial=1001,
        )
        self.assertNotIn("inventory", form.fields)
        self.assertNotIn("approval_reference", form.fields)
        self.assertNotIn("page_count", form.fields)
        self.assertNotIn("recipient_relation", form.fields)
        self.assertNotIn("recipient_identifier", form.fields)
        self.assertEqual(form.initial["serial_number"], 1001)
        self.assertEqual(
            form.initial["deposit_type"],
            BankSlip.DepositType.CASH_DEPOSIT,
        )

    def test_dmc_issuance_records_printed_serial_payment_and_is_permanent(self):
        issuance = self.issue_dmc()
        self.assertEqual(issuance.document_no, "1001")
        self.assertEqual(issuance.serial_number, 1001)
        self.assertEqual(issuance.payment_slip, self.shared_slip)
        self.assertEqual(issuance.amount_utilized, Decimal("1000.00"))
        self.assertEqual(issuance.semester_result, self.semester_result)
        self.assertFalse(issuance.is_reissue)

        with self.assertRaisesMessage(ValidationError, "permanent"):
            issuance.delete()
        with self.assertRaisesMessage(ValidationError, "permanent"):
            DocumentIssuance.objects.filter(pk=issuance.pk).delete()
        issuance.recipient_name = "Changed Recipient"
        with self.assertRaisesMessage(ValidationError, "cannot be edited"):
            issuance.save()

    def test_one_bank_slip_can_cover_several_students_and_document_types(self):
        first = self.issue_dmc()
        second = self.issue_dmc(
            serial_number=1002,
            semester_result=self.second_semester_result,
            recipient_name=self.second_student.name,
            amount_utilized="1200.00",
        )
        third = self.issue_transcript(
            serial_number=1003,
            amount_utilized="1500.00",
        )
        self.assertEqual(first.payment_slip, self.shared_slip)
        self.assertEqual(second.payment_slip, self.shared_slip)
        self.assertEqual(third.payment_slip, self.shared_slip)
        self.shared_slip.refresh_from_db()
        self.assertEqual(self.shared_slip.allocated_amount, Decimal("3700.00"))
        self.assertEqual(self.shared_slip.remaining_amount, Decimal("1300.00"))

    def test_bank_slip_cannot_be_over_allocated(self):
        self.issue_dmc(amount_utilized="4000.00")
        with self.assertRaisesMessage(ValidationError, "Only Rs. 1000.00 remains"):
            self.issue_dmc(
                serial_number=1002,
                semester_result=self.second_semester_result,
                recipient_name=self.second_student.name,
                amount_utilized="1200.00",
            )
        self.assertEqual(self.shared_slip.allocations.count(), 1)

    def test_new_bank_slip_can_be_created_during_issuance(self):
        issuance = self.issue_dmc(
            payment_slip=None,
            bank=self.bank,
            deposit_type=BankSlip.DepositType.ONLINE,
            bank_slip_no="ONLINE-NEW-001",
            bank_slip_date=date(2026, 8, 2),
            bank_slip_total_amount="3000.00",
            depositor_name="Test College",
            amount_utilized="1000.00",
        )
        self.assertEqual(issuance.payment_slip.slip_no, "ONLINE-NEW-001")
        self.assertEqual(issuance.payment_slip.total_amount, Decimal("3000.00"))
        self.assertEqual(issuance.payment_slip.remaining_amount, Decimal("2000.00"))

    def test_duplicate_new_slip_must_be_selected_as_existing(self):
        with self.assertRaisesMessage(ValidationError, "already exists"):
            self.issue_dmc(
                payment_slip=None,
                bank=self.bank,
                bank_slip_no="COLLEGE-SLIP-001",
                bank_slip_date=date(2026, 8, 2),
                bank_slip_total_amount="5000.00",
            )

    def test_printed_serial_is_unique_across_dmc_and_transcript(self):
        self.issue_dmc(serial_number=1001)
        with self.assertRaisesMessage(ValidationError, "already been recorded"):
            self.issue_transcript(serial_number=1001)

    def test_serial_must_be_inside_an_active_bundle(self):
        with self.assertRaisesMessage(ValidationError, "not inside any active sheet bundle"):
            self.issue_dmc(serial_number=9999)
        self.inventory.is_active = False
        self.inventory.save(update_fields=["is_active"])
        with self.assertRaisesMessage(ValidationError, "not inside any active sheet bundle"):
            self.issue_dmc(serial_number=1001)

    def test_duplicate_original_requires_reissue(self):
        original = self.issue_dmc()
        with self.assertRaisesMessage(ValidationError, "already been issued"):
            self.issue_dmc(serial_number=1002)
        self.assertTrue(DocumentIssuance.objects.filter(pk=original.pk).exists())

    def test_reissue_uses_new_serial_and_preserves_history(self):
        original = self.issue_dmc()
        reissue = self.issue_dmc(
            serial_number=1002,
            payment_slip=self.shared_slip,
            amount_utilized="500.00",
            reissue_of=original,
            reissue_reason="Original document was damaged.",
        )
        self.assertEqual(reissue.document_no, "1002")
        self.assertEqual(reissue.reissue_of, original)
        self.assertEqual(original.reissues.count(), 1)

    def test_reissue_reason_is_required(self):
        original = self.issue_dmc()
        with self.assertRaisesMessage(ValidationError, "reason is required"):
            self.issue_dmc(
                serial_number=1002,
                amount_utilized="500.00",
                reissue_of=original,
                reissue_reason="",
            )

    def test_used_inventory_cannot_be_renumbered_or_deleted(self):
        self.issue_dmc()
        self.inventory.refresh_from_db()
        self.inventory.bundle_size = 600
        with self.assertRaisesMessage(ValidationError, "cannot be changed"):
            self.inventory.save()
        self.inventory.refresh_from_db()
        with self.assertRaisesMessage(ValidationError, "cannot be deleted"):
            self.inventory.delete()

    def test_used_bank_and_bank_slip_are_protected(self):
        self.issue_dmc()
        self.bank.name = "Renamed Bank"
        with self.assertRaisesMessage(ValidationError, "cannot be changed"):
            self.bank.save()
        with self.assertRaisesMessage(ValidationError, "cannot be deleted"):
            self.bank.delete()

        self.shared_slip.total_amount = Decimal("9000.00")
        with self.assertRaisesMessage(ValidationError, "cannot be edited"):
            self.shared_slip.save()
        with self.assertRaisesMessage(ValidationError, "cannot be deleted"):
            self.shared_slip.delete()

    def test_registered_dmc_pdf_displays_printed_serial(self):
        issuance = self.issue_dmc()
        request = RequestFactory().get(
            reverse("dmc_batch_pdf", args=[self.batch.id]),
            {"enrollments": str(self.enrollment.id), "issuance": str(issuance.id)},
        )
        request.user = self.generator
        request.session = {}
        with patch("results.views.HTML") as html_class:
            html_class.return_value.write_pdf.return_value = b"%PDF-test"
            response = dmc_batch_pdf(request, self.batch.id)
        self.assertEqual(response.status_code, 200)
        self.assertIn("1001", html_class.call_args.kwargs["string"])

    def test_document_generator_can_open_register_and_bank_slips_but_not_setup(self):
        for url_name, view in (
            ("admin_document_issuance_register", document_issuance_register),
            ("admin_document_bank_slip_list", bank_slip_list),
        ):
            request = RequestFactory().get(reverse(url_name))
            request.user = self.generator
            request.session = {}
            response = view(request)
            self.assertEqual(response.status_code, 200)

        self.client.force_login(self.generator)
        for url_name in ("admin_document_inventory_list", "admin_document_bank_list"):
            response = self.client.get(reverse(url_name))
            self.assertEqual(response.status_code, 302)
            self.assertEqual(response.url, reverse("dashboard"))

    def test_controller_can_manage_inventory_and_banks(self):
        for url_name, view in (
            ("admin_document_inventory_list", document_inventory_list),
            ("admin_document_bank_list", bank_list),
        ):
            request = RequestFactory().get(reverse(url_name))
            request.user = self.controller
            request.session = {}
            response = view(request)
            self.assertEqual(response.status_code, 200)

        self.client.force_login(self.assistant)
        response = self.client.get(reverse("admin_issue_dmc", args=[self.semester_result.id]))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse("dashboard"))
