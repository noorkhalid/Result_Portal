from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.db.models import Sum

from results.dmc_services import evaluate_dmc_eligibility
from results.models import ResultBatch, SemesterResult
from results.transcript_services import evaluate_transcript_eligibility
from students.models import Enrollment

from .models import Bank, BankSlip, DocumentInventory, DocumentIssuance


def next_available_serial() -> int | None:
    """Return the first unused serial from active common sheet bundles."""

    for inventory in DocumentInventory.objects.filter(is_active=True).order_by(
        "start_number", "id"
    ):
        used = set(
            inventory.issuances.values_list("serial_number", flat=True)
        )
        for serial in range(inventory.start_number, inventory.end_number + 1):
            if serial not in used:
                return serial
    return None


def inventory_for_serial(serial_number: int, *, active_only: bool = True):
    queryset = DocumentInventory.objects.all()
    if active_only:
        queryset = queryset.filter(is_active=True)
    return queryset.filter(
        start_number__lte=serial_number,
        end_number__gte=serial_number,
    ).order_by("start_number", "id").first()


def _existing_initial_issuance(
    *,
    document_type: str,
    enrollment_id: int,
    semester_result_id: int | None,
):
    qs = DocumentIssuance.objects.filter(
        document_type=document_type,
        enrollment_id=enrollment_id,
        reissue_of__isnull=True,
    )
    if document_type == DocumentInventory.DocumentType.DMC:
        qs = qs.filter(semester_result_id=semester_result_id)
    else:
        qs = qs.filter(semester_result__isnull=True)
    return qs.order_by("id").first()


def _decimal_amount(value, message: str) -> Decimal:
    try:
        amount = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationError(message) from exc
    if amount <= 0:
        raise ValidationError(message)
    return amount


def create_document_issuance(
    *,
    document_type: str,
    issued_by,
    serial_number: int,
    issue_date: date,
    amount_utilized,
    recipient_name: str,
    payment_slip: BankSlip | None = None,
    bank: Bank | None = None,
    deposit_type: str = BankSlip.DepositType.CASH_DEPOSIT,
    bank_slip_no: str = "",
    bank_slip_date: date | None = None,
    bank_slip_total_amount=None,
    depositor_name: str = "",
    payment_remarks: str = "",
    remarks: str = "",
    semester_result: SemesterResult | None = None,
    enrollment: Enrollment | None = None,
    source_batch: ResultBatch | None = None,
    reissue_of: DocumentIssuance | None = None,
    reissue_reason: str = "",
) -> DocumentIssuance:
    """Issue one preprinted sheet and allocate payment from a reusable bank slip."""

    if document_type not in DocumentInventory.DocumentType.values:
        raise ValidationError("Invalid document type.")
    try:
        serial_number = int(serial_number)
    except (TypeError, ValueError) as exc:
        raise ValidationError("Enter the serial number printed on the physical sheet.") from exc
    if serial_number < 1:
        raise ValidationError("Printed serial number must be at least 1.")
    amount_utilized = _decimal_amount(
        amount_utilized,
        "Amount used for this document must be greater than zero.",
    )

    with transaction.atomic():
        inventory = (
            DocumentInventory.objects.select_for_update()
            .filter(
                is_active=True,
                start_number__lte=serial_number,
                end_number__gte=serial_number,
            )
            .first()
        )
        if not inventory:
            raise ValidationError(
                "The printed serial number is not inside any active sheet bundle."
            )
        if DocumentIssuance.objects.filter(
            inventory=inventory,
            serial_number=serial_number,
        ).exists():
            raise ValidationError(
                "This printed serial number has already been recorded as issued."
            )

        if payment_slip is not None:
            locked_slip = (
                BankSlip.objects.select_for_update()
                .select_related("bank")
                .get(pk=payment_slip.pk)
            )
        else:
            if not bank or not getattr(bank, "pk", None):
                raise ValidationError("Select a bank for the new payment slip.")
            bank = Bank.objects.get(pk=bank.pk)
            if not bank.is_active:
                raise ValidationError("The selected bank is inactive.")
            if deposit_type not in BankSlip.DepositType.values:
                raise ValidationError("Select a valid deposit type.")
            bank_slip_no = (bank_slip_no or "").strip()
            if not bank_slip_no or not bank_slip_date:
                raise ValidationError(
                    "Complete bank slip details are required. No document can be issued without payment evidence."
                )
            bank_slip_total_amount = _decimal_amount(
                bank_slip_total_amount,
                "Total deposited amount must be greater than zero.",
            )
            if amount_utilized > bank_slip_total_amount:
                raise ValidationError(
                    "Amount used for this document cannot exceed the total deposited amount."
                )
            duplicate = BankSlip(
                bank=bank,
                deposit_type=deposit_type,
                slip_no=bank_slip_no,
                deposit_date=bank_slip_date,
                total_amount=bank_slip_total_amount,
                depositor_name=depositor_name,
                remarks=payment_remarks,
                created_by=issued_by,
            )
            duplicate.full_clean(exclude=None, validate_unique=False, validate_constraints=False)
            if BankSlip.objects.filter(
                bank=bank,
                slip_no_normalized=duplicate.slip_no_normalized,
                deposit_date=bank_slip_date,
            ).exists():
                raise ValidationError(
                    "This bank slip already exists. Select it from Existing Bank Slip so its remaining balance can be used."
                )
            locked_slip = duplicate
            try:
                locked_slip.save()
            except IntegrityError as exc:
                raise ValidationError(
                    "This bank slip already exists. Select it from Existing Bank Slip."
                ) from exc

        already_allocated = locked_slip.allocations.aggregate(
            total=Sum("amount_utilized")
        )["total"] or Decimal("0.00")
        remaining = Decimal(locked_slip.total_amount) - already_allocated
        if amount_utilized > remaining:
            raise ValidationError(
                f"Only Rs. {remaining:.2f} remains available on the selected bank slip."
            )

        if document_type == DocumentInventory.DocumentType.DMC:
            if not semester_result or not semester_result.pk:
                raise ValidationError("Select a semester result for DMC issuance.")
            locked_result = (
                SemesterResult.objects.select_for_update()
                .select_related(
                    "batch",
                    "batch__curriculum",
                    "enrollment",
                    "enrollment__student",
                )
                .get(pk=semester_result.pk)
            )
            eligibility = evaluate_dmc_eligibility(locked_result)
            if not eligibility.is_eligible:
                raise ValidationError(f"DMC cannot be issued: {eligibility.reason}")
            enrollment = locked_result.enrollment
            source_batch = locked_result.batch
            semester_result = locked_result
        else:
            if not enrollment or not enrollment.pk:
                raise ValidationError("Select an enrollment for transcript issuance.")
            enrollment = (
                Enrollment.objects.select_for_update()
                .select_related("student", "program", "session", "curriculum")
                .get(pk=enrollment.pk)
            )
            eligibility = evaluate_transcript_eligibility(enrollment)
            if not eligibility.is_eligible:
                raise ValidationError(
                    f"Transcript cannot be issued: {eligibility.reason}"
                )
            if not source_batch or not source_batch.pk:
                raise ValidationError(
                    "A final-semester source batch is required for transcript issuance."
                )
            source_batch = ResultBatch.objects.select_related("curriculum").get(
                pk=source_batch.pk
            )
            if not source_batch.is_final_semester:
                raise ValidationError(
                    "A transcript must use a final-semester result batch."
                )
            semester_result = None

        if reissue_of:
            reissue_of = (
                DocumentIssuance.objects.select_for_update()
                .select_related("enrollment", "semester_result", "source_batch")
                .get(pk=reissue_of.pk)
            )
            if not (reissue_reason or "").strip():
                raise ValidationError("A reason is required for reissuance.")
        else:
            existing = _existing_initial_issuance(
                document_type=document_type,
                enrollment_id=enrollment.id,
                semester_result_id=(semester_result.id if semester_result else None),
            )
            if existing:
                raise ValidationError(
                    f'Document "{existing.document_no}" has already been issued. Use Reissue instead.'
                )

        try:
            issuance = DocumentIssuance.objects.create(
                document_type=document_type,
                inventory=inventory,
                serial_number=serial_number,
                document_no=str(serial_number),
                enrollment=enrollment,
                semester_result=semester_result,
                source_batch=source_batch,
                issue_date=issue_date,
                payment_slip=locked_slip,
                amount_utilized=amount_utilized,
                recipient_name=recipient_name,
                remarks=remarks,
                issued_by=issued_by,
                reissue_of=reissue_of,
                reissue_reason=reissue_reason,
            )
        except IntegrityError as exc:
            raise ValidationError(
                "The printed serial number has already been recorded. Refresh and verify the data."
            ) from exc

        return issuance
