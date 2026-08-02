from __future__ import annotations

import re
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.db.models import Sum
from django.utils import timezone

from results.models import ResultBatch, SemesterResult
from students.models import Enrollment


def normalize_slip_number(value: str) -> str:
    return re.sub(r"[^A-Z0-9]", "", (value or "").upper())


class ProtectedUsedQuerySet(models.QuerySet):
    protected_message = "This record is already in use and cannot be deleted."

    def delete(self):
        for obj in self:
            if getattr(obj, "is_in_use", False):
                raise ValidationError(self.protected_message)
        return super().delete()


class BankQuerySet(ProtectedUsedQuerySet):
    protected_message = "A bank used in payment records cannot be deleted. Deactivate it instead."


class Bank(models.Model):
    """Bank setup used by official document payment slips."""

    name = models.CharField(max_length=120, unique=True)
    sort_order = models.PositiveSmallIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_document_banks",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = BankQuerySet.as_manager()

    class Meta:
        ordering = ["sort_order", "name"]

    def clean(self):
        super().clean()
        self.name = (self.name or "").strip()
        if not self.name:
            raise ValidationError({"name": "Bank name is required."})
        if self.pk and Bank.objects.filter(pk=self.pk).exists():
            previous = Bank.objects.get(pk=self.pk)
            if previous.payment_slips.exists() and previous.name != self.name:
                raise ValidationError(
                    {"name": "The bank name cannot be changed after payment slips have been recorded."}
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def is_in_use(self) -> bool:
        return bool(self.pk and self.payment_slips.exists())

    def delete(self, *args, **kwargs):
        if self.is_in_use:
            raise ValidationError(
                "A bank used in payment records cannot be deleted. Deactivate it instead."
            )
        return super().delete(*args, **kwargs)

    def __str__(self) -> str:
        return self.name


class DocumentInventoryQuerySet(ProtectedUsedQuerySet):
    protected_message = "Used document inventory cannot be deleted. Deactivate it instead."


class DocumentInventory(models.Model):
    """One common bundle of preprinted sheets used for DMCs and transcripts."""

    class DocumentType(models.TextChoices):
        DMC = "dmc", "DMC"
        TRANSCRIPT = "transcript", "Transcript"

    start_number = models.PositiveIntegerField()
    bundle_size = models.PositiveIntegerField(
        default=500,
        help_text="Number of sheets in the bundle. The end serial is calculated automatically.",
    )
    end_number = models.PositiveIntegerField(editable=False)
    received_date = models.DateField(default=timezone.localdate)
    is_active = models.BooleanField(default=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_document_inventories",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = DocumentInventoryQuerySet.as_manager()

    class Meta:
        ordering = ["start_number", "id"]
        verbose_name_plural = "Document inventories"
        indexes = [
            models.Index(fields=["is_active", "start_number"], name="doc_inv_active_start_idx")
        ]

    def clean(self):
        super().clean()
        if self.start_number is None or self.start_number < 1:
            raise ValidationError({"start_number": "Start serial number must be at least 1."})
        if self.bundle_size is None or self.bundle_size < 1:
            raise ValidationError({"bundle_size": "Bundle size must be at least 1."})
        if self.bundle_size > 100000:
            raise ValidationError({"bundle_size": "Bundle size is unreasonably large."})

        self.end_number = int(self.start_number) + int(self.bundle_size) - 1
        overlap = DocumentInventory.objects.filter(
            start_number__lte=self.end_number,
            end_number__gte=self.start_number,
        ).exclude(pk=self.pk)
        if overlap.exists():
            raise ValidationError("This serial-number range overlaps an existing sheet bundle.")

        if self.pk and DocumentInventory.objects.filter(pk=self.pk).exists():
            previous = DocumentInventory.objects.get(pk=self.pk)
            if previous.issuances.exists():
                changed = any(
                    getattr(previous, field) != getattr(self, field)
                    for field in ("start_number", "bundle_size", "end_number")
                )
                if changed:
                    raise ValidationError(
                        "The serial range cannot be changed after any sheet from the bundle has been issued."
                    )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def total_count(self) -> int:
        return int(self.bundle_size or 0)

    @property
    def used_count(self) -> int:
        if not self.pk:
            return 0
        return self.issuances.count()

    @property
    def available_count(self) -> int:
        return max(self.total_count - self.used_count, 0)

    @property
    def is_exhausted(self) -> bool:
        return self.available_count == 0

    @property
    def first_document_no(self) -> str:
        return str(self.start_number)

    @property
    def last_document_no(self) -> str:
        return str(self.end_number)

    @property
    def is_in_use(self) -> bool:
        return bool(self.pk and self.issuances.exists())

    def delete(self, *args, **kwargs):
        if self.is_in_use:
            raise ValidationError(
                "Used document inventory cannot be deleted. Deactivate it instead."
            )
        return super().delete(*args, **kwargs)

    def __str__(self) -> str:
        return f"Sheets {self.start_number}–{self.end_number} ({self.bundle_size})"


class BankSlipQuerySet(ProtectedUsedQuerySet):
    protected_message = "A bank slip used for document issuance cannot be deleted."


class BankSlip(models.Model):
    """A payment slip that may fund one or several document issuances."""

    class DepositType(models.TextChoices):
        CASH_DEPOSIT = "cash_deposit", "Cash Deposit"
        ONLINE = "online", "Online Transfer"
        CHEQUE = "cheque", "Cheque"
        PAY_ORDER = "pay_order", "Pay Order"
        OTHER = "other", "Other"

    bank = models.ForeignKey(
        Bank,
        on_delete=models.PROTECT,
        related_name="payment_slips",
    )
    deposit_type = models.CharField(
        max_length=20,
        choices=DepositType.choices,
        default=DepositType.CASH_DEPOSIT,
    )
    slip_no = models.CharField(
        max_length=120,
        help_text="Bank slip number, transaction ID, cheque number, or pay-order number.",
    )
    slip_no_normalized = models.CharField(max_length=120, editable=False)
    deposit_date = models.DateField()
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    depositor_name = models.CharField(
        max_length=200,
        blank=True,
        help_text="Optional student, college, or depositor name.",
    )
    remarks = models.CharField(max_length=255, blank=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_document_bank_slips",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    objects = BankSlipQuerySet.as_manager()

    class Meta:
        ordering = ["-deposit_date", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["bank", "slip_no_normalized", "deposit_date"],
                name="unique_document_bank_slip",
            )
        ]
        indexes = [
            models.Index(fields=["deposit_date", "slip_no_normalized"], name="doc_slip_date_no_idx"),
            models.Index(fields=["bank", "deposit_date"], name="doc_slip_bank_date_idx"),
        ]

    def clean(self):
        super().clean()
        self.slip_no = (self.slip_no or "").strip()
        self.slip_no_normalized = normalize_slip_number(self.slip_no)
        self.depositor_name = (self.depositor_name or "").strip()
        self.remarks = (self.remarks or "").strip()
        if not self.slip_no_normalized:
            raise ValidationError({"slip_no": "Bank slip number or transaction ID is required."})
        if not self.deposit_date:
            raise ValidationError({"deposit_date": "Deposit date is required."})
        if self.deposit_date and self.deposit_date > timezone.localdate():
            raise ValidationError({"deposit_date": "Deposit date cannot be in the future."})
        if self.total_amount is None or self.total_amount <= 0:
            raise ValidationError({"total_amount": "Total deposited amount must be greater than zero."})

        if self.pk and BankSlip.objects.filter(pk=self.pk).exists():
            previous = BankSlip.objects.get(pk=self.pk)
            if previous.allocations.exists():
                immutable_fields = (
                    "bank_id",
                    "deposit_type",
                    "slip_no",
                    "slip_no_normalized",
                    "deposit_date",
                    "total_amount",
                    "depositor_name",
                    "remarks",
                )
                if any(
                    getattr(previous, field) != getattr(self, field)
                    for field in immutable_fields
                ):
                    raise ValidationError(
                        "A bank slip cannot be edited after any amount has been allocated."
                    )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def allocated_amount(self) -> Decimal:
        if not self.pk:
            return Decimal("0.00")
        return self.allocations.aggregate(total=Sum("amount_utilized"))["total"] or Decimal("0.00")

    @property
    def remaining_amount(self) -> Decimal:
        return max(Decimal(self.total_amount or 0) - self.allocated_amount, Decimal("0.00"))

    @property
    def is_fully_allocated(self) -> bool:
        return self.remaining_amount <= 0

    @property
    def is_in_use(self) -> bool:
        return bool(self.pk and self.allocations.exists())

    def delete(self, *args, **kwargs):
        if self.is_in_use:
            raise ValidationError("A bank slip used for document issuance cannot be deleted.")
        return super().delete(*args, **kwargs)

    def __str__(self) -> str:
        return f"{self.bank.name} | {self.slip_no} | {self.deposit_date:%d-%m-%Y}"


class ProtectedDocumentIssuanceQuerySet(models.QuerySet):
    def delete(self):
        raise ValidationError("Document issuance history is permanent and cannot be deleted.")


class DocumentIssuance(models.Model):
    """Permanent register entry for an issued or reissued official document."""

    DepositType = BankSlip.DepositType

    document_type = models.CharField(
        max_length=20,
        choices=DocumentInventory.DocumentType.choices,
    )
    inventory = models.ForeignKey(
        DocumentInventory,
        on_delete=models.PROTECT,
        related_name="issuances",
    )
    serial_number = models.PositiveIntegerField()
    document_no = models.CharField(max_length=100, unique=True)

    enrollment = models.ForeignKey(
        Enrollment,
        on_delete=models.PROTECT,
        related_name="document_issuances",
    )
    semester_result = models.ForeignKey(
        SemesterResult,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="document_issuances",
    )
    source_batch = models.ForeignKey(
        ResultBatch,
        on_delete=models.PROTECT,
        related_name="document_issuances",
    )

    issue_date = models.DateField(default=timezone.localdate)
    payment_slip = models.ForeignKey(
        BankSlip,
        on_delete=models.PROTECT,
        related_name="allocations",
    )
    amount_utilized = models.DecimalField(max_digits=12, decimal_places=2)
    recipient_name = models.CharField(max_length=200)
    remarks = models.CharField(max_length=255, blank=True)

    issued_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="issued_documents",
    )
    reissue_of = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="reissues",
    )
    reissue_reason = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = ProtectedDocumentIssuanceQuerySet.as_manager()

    class Meta:
        ordering = ["-issue_date", "-id"]
        constraints = [
            models.UniqueConstraint(
                fields=["inventory", "serial_number"],
                name="unique_document_inventory_serial",
            )
        ]
        indexes = [
            models.Index(fields=["document_type", "issue_date"], name="doc_issue_type_date_idx"),
            models.Index(fields=["enrollment"], name="doc_issue_enrollment_idx"),
            models.Index(fields=["payment_slip"], name="doc_issue_payment_slip_idx"),
        ]

    def clean(self):
        super().clean()
        self.document_no = (self.document_no or "").strip()
        self.recipient_name = (self.recipient_name or "").strip()
        self.remarks = (self.remarks or "").strip()
        self.reissue_reason = (self.reissue_reason or "").strip()

        if self.inventory_id:
            if not (self.inventory.start_number <= self.serial_number <= self.inventory.end_number):
                raise ValidationError({"serial_number": "Serial number is outside the recorded sheet bundle."})
            expected_no = str(self.serial_number)
            if self.document_no != expected_no:
                raise ValidationError({"document_no": f'Document number must be "{expected_no}".'})

        if self.issue_date and self.issue_date > timezone.localdate():
            raise ValidationError({"issue_date": "Issue date cannot be in the future."})
        if self.amount_utilized is None or self.amount_utilized <= 0:
            raise ValidationError({"amount_utilized": "Amount utilized must be greater than zero."})
        if not self.recipient_name:
            raise ValidationError({"recipient_name": "Recipient name is required."})

        if self.payment_slip_id and self.amount_utilized:
            other_allocated = self.payment_slip.allocations.exclude(pk=self.pk).aggregate(
                total=Sum("amount_utilized")
            )["total"] or Decimal("0.00")
            if other_allocated + Decimal(self.amount_utilized) > Decimal(self.payment_slip.total_amount):
                raise ValidationError(
                    {"amount_utilized": "This allocation exceeds the remaining balance of the selected bank slip."}
                )

        if self.semester_result_id:
            if self.semester_result.enrollment_id != self.enrollment_id:
                raise ValidationError({"semester_result": "Semester result does not belong to this enrollment."})
            if self.semester_result.batch_id != self.source_batch_id:
                raise ValidationError({"source_batch": "Source batch must match the DMC semester result."})

        if self.source_batch_id:
            if self.source_batch.department_id != self.enrollment.department_id:
                raise ValidationError({"source_batch": "Source batch department does not match the enrollment."})
            if self.source_batch.program_id != self.enrollment.program_id:
                raise ValidationError({"source_batch": "Source batch program does not match the enrollment."})
            if self.source_batch.session_id != self.enrollment.session_id:
                raise ValidationError({"source_batch": "Source batch session does not match the enrollment."})

        if self.document_type == DocumentInventory.DocumentType.DMC:
            if not self.semester_result_id:
                raise ValidationError({"semester_result": "A DMC issuance requires a semester result."})
        elif self.document_type == DocumentInventory.DocumentType.TRANSCRIPT:
            if self.semester_result_id:
                raise ValidationError({"semester_result": "A transcript issuance must not use one semester result."})
            if self.source_batch_id and not self.source_batch.is_final_semester:
                raise ValidationError({"source_batch": "A transcript must use a final-semester result batch."})

        if self.reissue_of_id:
            original = self.reissue_of
            if not self.reissue_reason:
                raise ValidationError({"reissue_reason": "A reason is required for reissuance."})
            if original.document_type != self.document_type:
                raise ValidationError({"reissue_of": "Reissue document type must match the original issuance."})
            if original.enrollment_id != self.enrollment_id:
                raise ValidationError({"reissue_of": "Reissue enrollment must match the original issuance."})
            if original.semester_result_id != self.semester_result_id:
                raise ValidationError({"reissue_of": "Reissue result must match the original issuance."})
        elif self.reissue_reason:
            raise ValidationError({"reissue_reason": "Reissue reason is only allowed for a reissued document."})

        if not self.reissue_of_id and self.enrollment_id:
            duplicate = DocumentIssuance.objects.filter(
                document_type=self.document_type,
                enrollment_id=self.enrollment_id,
                reissue_of__isnull=True,
            ).exclude(pk=self.pk)
            if self.document_type == DocumentInventory.DocumentType.DMC:
                duplicate = duplicate.filter(semester_result_id=self.semester_result_id)
            else:
                duplicate = duplicate.filter(semester_result__isnull=True)
            if duplicate.exists():
                raise ValidationError("This document has already been issued. Use the Reissue action instead.")

        if self.pk and DocumentIssuance.objects.filter(pk=self.pk).exists():
            previous = DocumentIssuance.objects.get(pk=self.pk)
            immutable_fields = (
                "document_type",
                "inventory_id",
                "serial_number",
                "document_no",
                "enrollment_id",
                "semester_result_id",
                "source_batch_id",
                "issue_date",
                "payment_slip_id",
                "amount_utilized",
                "recipient_name",
                "remarks",
                "issued_by_id",
                "reissue_of_id",
                "reissue_reason",
            )
            if any(getattr(previous, field) != getattr(self, field) for field in immutable_fields):
                raise ValidationError(
                    "Document issuance records are permanent and cannot be edited. Create a reissue when required."
                )

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)

    @property
    def is_reissue(self) -> bool:
        return bool(self.reissue_of_id)

    @property
    def student(self):
        return self.enrollment.student

    @property
    def document_label(self) -> str:
        if self.document_type == DocumentInventory.DocumentType.DMC:
            return f"DMC — Semester {self.source_batch.semester_number}"
        return "Academic Transcript"

    def delete(self, *args, **kwargs):
        raise ValidationError("Document issuance history is permanent and cannot be deleted.")

    def __str__(self) -> str:
        return f"{self.document_no} | {self.enrollment.roll_no} | {self.get_document_type_display()}"
