from django.contrib import admin

from .models import Bank, BankSlip, DocumentInventory, DocumentIssuance


@admin.register(Bank)
class BankAdmin(admin.ModelAdmin):
    list_display = ("name", "sort_order", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name",)


@admin.register(DocumentInventory)
class DocumentInventoryAdmin(admin.ModelAdmin):
    list_display = (
        "start_number",
        "end_number",
        "bundle_size",
        "received_date",
        "is_active",
        "used_count",
        "available_count",
    )
    list_filter = ("is_active", "received_date")
    search_fields = ("start_number", "end_number")


@admin.register(BankSlip)
class BankSlipAdmin(admin.ModelAdmin):
    list_display = (
        "slip_no",
        "bank",
        "deposit_type",
        "deposit_date",
        "total_amount",
        "allocated_amount",
        "remaining_amount",
        "depositor_name",
    )
    list_filter = ("bank", "deposit_type", "deposit_date")
    search_fields = ("slip_no", "depositor_name", "bank__name")


@admin.register(DocumentIssuance)
class DocumentIssuanceAdmin(admin.ModelAdmin):
    list_display = (
        "document_no",
        "document_type",
        "student",
        "issue_date",
        "payment_slip",
        "amount_utilized",
        "issued_by",
        "is_reissue",
    )
    list_filter = ("document_type", "issue_date", "payment_slip__bank")
    search_fields = (
        "document_no",
        "enrollment__roll_no",
        "enrollment__student__registration_no",
        "enrollment__student__name",
        "payment_slip__slip_no",
        "payment_slip__depositor_name",
    )
