from __future__ import annotations

from decimal import Decimal

from django import forms
from django.db.models import DecimalField, F, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from .models import Bank, BankSlip, DocumentInventory


class BankForm(forms.ModelForm):
    class Meta:
        model = Bank
        fields = ["name", "sort_order", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            else:
                field.widget.attrs.setdefault("class", "form-control")


class DocumentInventoryForm(forms.ModelForm):
    class Meta:
        model = DocumentInventory
        fields = ["start_number", "bundle_size", "received_date", "is_active"]
        labels = {
            "start_number": "Start Serial No.",
            "bundle_size": "Bundle Size",
            "received_date": "Received Date",
            "is_active": "Active",
        }
        widgets = {
            "received_date": forms.DateInput(attrs={"type": "date"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["bundle_size"].initial = self.instance.bundle_size if self.instance.pk else 500
        for field in self.fields.values():
            if isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.setdefault("class", "form-check-input")
            else:
                field.widget.attrs.setdefault("class", "form-control")
        if self.instance.pk and self.instance.issuances.exists():
            self.fields["start_number"].disabled = True
            self.fields["bundle_size"].disabled = True


class BankSlipForm(forms.ModelForm):
    class Meta:
        model = BankSlip
        fields = [
            "bank",
            "deposit_type",
            "slip_no",
            "deposit_date",
            "total_amount",
            "depositor_name",
            "remarks",
        ]
        labels = {
            "slip_no": "Bank Slip No. / Transaction ID",
            "deposit_date": "Deposit Date",
            "total_amount": "Total Deposited Amount",
            "depositor_name": "Depositor / College Name (Optional)",
        }
        widgets = {
            "deposit_date": forms.DateInput(attrs={"type": "date"}),
            "remarks": forms.Textarea(attrs={"rows": 2}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["bank"].queryset = Bank.objects.filter(is_active=True).order_by("sort_order", "name")
        self.fields["deposit_type"].initial = BankSlip.DepositType.CASH_DEPOSIT
        for field in self.fields.values():
            if isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault("class", "form-select")
            else:
                field.widget.attrs.setdefault("class", "form-control")
        if self.instance.pk and self.instance.allocations.exists():
            for field in self.fields.values():
                field.disabled = True


class AvailableBankSlipChoiceField(forms.ModelChoiceField):
    def label_from_instance(self, obj):
        allocated = getattr(obj, "allocated_total", None)
        if allocated is None:
            allocated = obj.allocated_amount
        remaining = Decimal(obj.total_amount) - Decimal(allocated or 0)
        depositor = f" | {obj.depositor_name}" if obj.depositor_name else ""
        return (
            f"{obj.bank.name} | {obj.slip_no} | {obj.deposit_date:%d-%m-%Y}"
            f" | Available Rs. {remaining:.2f}{depositor}"
        )


class DocumentIssuanceForm(forms.Form):
    PAYMENT_NEW = "new"
    PAYMENT_EXISTING = "existing"
    PAYMENT_SOURCE_CHOICES = (
        (PAYMENT_NEW, "Record New Bank Slip"),
        (PAYMENT_EXISTING, "Use Existing Bank Slip"),
    )

    serial_number = forms.IntegerField(
        min_value=1,
        label="Printed Serial No.",
        help_text="The next unused printed serial is suggested automatically. You may edit it.",
    )
    issue_date = forms.DateField(
        initial=timezone.localdate,
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    payment_source = forms.ChoiceField(
        choices=PAYMENT_SOURCE_CHOICES,
        initial=PAYMENT_NEW,
        label="Payment Entry",
    )
    existing_payment_slip = AvailableBankSlipChoiceField(
        queryset=BankSlip.objects.none(),
        required=False,
        label="Existing Bank Slip",
        help_text="Select a slip that still has an available balance.",
    )
    bank = forms.ModelChoiceField(
        queryset=Bank.objects.none(),
        required=False,
        label="Bank",
    )
    deposit_type = forms.ChoiceField(
        choices=BankSlip.DepositType.choices,
        required=False,
        initial=BankSlip.DepositType.CASH_DEPOSIT,
        label="Deposit Type",
    )
    bank_slip_no = forms.CharField(
        max_length=120,
        required=False,
        label="Bank Slip No. / Transaction ID",
    )
    bank_slip_date = forms.DateField(
        required=False,
        label="Bank Slip Date",
        widget=forms.DateInput(attrs={"type": "date"}),
    )
    bank_slip_total_amount = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=0.01,
        required=False,
        label="Total Deposited Amount",
        help_text="The full amount deposited on this slip, even when it covers several students.",
    )
    depositor_name = forms.CharField(
        max_length=200,
        required=False,
        label="Depositor / College Name (Optional)",
    )
    amount_utilized = forms.DecimalField(
        max_digits=12,
        decimal_places=2,
        min_value=0.01,
        label="Amount Used for This Document",
    )
    recipient_name = forms.CharField(max_length=200)
    remarks = forms.CharField(
        max_length=255,
        required=False,
        widget=forms.Textarea(attrs={"rows": 2}),
    )

    def __init__(
        self,
        *args,
        recipient_name: str = "",
        suggested_serial: int | None = None,
        **kwargs,
    ):
        super().__init__(*args, **kwargs)
        self.fields["bank"].queryset = Bank.objects.filter(is_active=True).order_by("sort_order", "name")
        available_slips = (
            BankSlip.objects.select_related("bank")
            .annotate(
                allocated_total=Coalesce(
                    Sum("allocations__amount_utilized"),
                    Value(Decimal("0.00")),
                    output_field=DecimalField(max_digits=12, decimal_places=2),
                )
            )
            .filter(total_amount__gt=F("allocated_total"))
            .order_by("-deposit_date", "-id")
        )
        self.fields["existing_payment_slip"].queryset = available_slips

        if not self.is_bound:
            if recipient_name:
                self.initial["recipient_name"] = recipient_name
            if suggested_serial is not None:
                self.initial["serial_number"] = suggested_serial
            self.initial["payment_source"] = self.PAYMENT_NEW
            self.initial["deposit_type"] = BankSlip.DepositType.CASH_DEPOSIT

        for name, field in self.fields.items():
            if isinstance(field.widget, forms.Select):
                field.widget.attrs.setdefault("class", "form-select")
            else:
                field.widget.attrs.setdefault("class", "form-control")
            if name in {
                "bank",
                "deposit_type",
                "bank_slip_no",
                "bank_slip_date",
                "bank_slip_total_amount",
                "depositor_name",
            }:
                field.widget.attrs["data-payment-new"] = "1"
            if name == "existing_payment_slip":
                field.widget.attrs["data-payment-existing"] = "1"

    def clean(self):
        cleaned = super().clean()
        source = cleaned.get("payment_source")
        amount = cleaned.get("amount_utilized")

        if source == self.PAYMENT_EXISTING:
            slip = cleaned.get("existing_payment_slip")
            if not slip:
                self.add_error("existing_payment_slip", "Select an existing bank slip.")
            elif amount and amount > slip.remaining_amount:
                self.add_error(
                    "amount_utilized",
                    f"Only Rs. {slip.remaining_amount:.2f} remains available on this bank slip.",
                )
        elif source == self.PAYMENT_NEW:
            required = {
                "bank": "Select a bank.",
                "deposit_type": "Select a deposit type.",
                "bank_slip_no": "Enter the bank slip number or transaction ID.",
                "bank_slip_date": "Enter the bank slip date.",
                "bank_slip_total_amount": "Enter the total deposited amount.",
            }
            for name, message in required.items():
                if not cleaned.get(name):
                    self.add_error(name, message)
            slip_date = cleaned.get("bank_slip_date")
            if slip_date and slip_date > timezone.localdate():
                self.add_error("bank_slip_date", "Bank slip date cannot be in the future.")
            total = cleaned.get("bank_slip_total_amount")
            if amount and total and amount > total:
                self.add_error(
                    "amount_utilized",
                    "Amount used for this document cannot exceed the total deposited amount.",
                )
        else:
            self.add_error("payment_source", "Select how the bank slip will be recorded.")

        return cleaned


class DocumentReissueForm(DocumentIssuanceForm):
    reissue_reason = forms.CharField(
        max_length=255,
        widget=forms.Textarea(attrs={"rows": 3}),
        label="Reason for Reissue",
    )
