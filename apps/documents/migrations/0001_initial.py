# Generated for the final Document Issuance Register, common sheet inventory,
# bank setup, and reusable bank-slip allocation workflow.

import django.db.models.deletion
import django.utils.timezone
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("results", "0016_extensible_hold_categories"),
        ("students", "0005_alter_enrollment_curriculum"),
    ]

    operations = [
        migrations.CreateModel(
            name="Bank",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("name", models.CharField(max_length=120, unique=True)),
                ("sort_order", models.PositiveSmallIntegerField(default=0)),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="created_document_banks",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["sort_order", "name"]},
        ),
        migrations.CreateModel(
            name="DocumentInventory",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("start_number", models.PositiveIntegerField()),
                (
                    "bundle_size",
                    models.PositiveIntegerField(
                        default=500,
                        help_text="Number of sheets in the bundle. The end serial is calculated automatically.",
                    ),
                ),
                ("end_number", models.PositiveIntegerField(editable=False)),
                (
                    "received_date",
                    models.DateField(default=django.utils.timezone.localdate),
                ),
                ("is_active", models.BooleanField(default=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="created_document_inventories",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={
                "verbose_name_plural": "Document inventories",
                "ordering": ["start_number", "id"],
            },
        ),
        migrations.CreateModel(
            name="BankSlip",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "deposit_type",
                    models.CharField(
                        choices=[
                            ("cash_deposit", "Cash Deposit"),
                            ("online", "Online Transfer"),
                            ("cheque", "Cheque"),
                            ("pay_order", "Pay Order"),
                            ("other", "Other"),
                        ],
                        default="cash_deposit",
                        max_length=20,
                    ),
                ),
                (
                    "slip_no",
                    models.CharField(
                        help_text="Bank slip number, transaction ID, cheque number, or pay-order number.",
                        max_length=120,
                    ),
                ),
                (
                    "slip_no_normalized",
                    models.CharField(editable=False, max_length=120),
                ),
                ("deposit_date", models.DateField()),
                (
                    "total_amount",
                    models.DecimalField(decimal_places=2, max_digits=12),
                ),
                (
                    "depositor_name",
                    models.CharField(
                        blank=True,
                        help_text="Optional student, college, or depositor name.",
                        max_length=200,
                    ),
                ),
                ("remarks", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "bank",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="payment_slips",
                        to="documents.bank",
                    ),
                ),
                (
                    "created_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="created_document_bank_slips",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
            ],
            options={"ordering": ["-deposit_date", "-id"]},
        ),
        migrations.CreateModel(
            name="DocumentIssuance",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "document_type",
                    models.CharField(
                        choices=[("dmc", "DMC"), ("transcript", "Transcript")],
                        max_length=20,
                    ),
                ),
                ("serial_number", models.PositiveIntegerField()),
                ("document_no", models.CharField(max_length=100, unique=True)),
                (
                    "issue_date",
                    models.DateField(default=django.utils.timezone.localdate),
                ),
                (
                    "amount_utilized",
                    models.DecimalField(decimal_places=2, max_digits=12),
                ),
                ("recipient_name", models.CharField(max_length=200)),
                ("remarks", models.CharField(blank=True, max_length=255)),
                ("reissue_reason", models.CharField(blank=True, max_length=255)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                (
                    "enrollment",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="document_issuances",
                        to="students.enrollment",
                    ),
                ),
                (
                    "inventory",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="issuances",
                        to="documents.documentinventory",
                    ),
                ),
                (
                    "issued_by",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="issued_documents",
                        to=settings.AUTH_USER_MODEL,
                    ),
                ),
                (
                    "payment_slip",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="allocations",
                        to="documents.bankslip",
                    ),
                ),
                (
                    "reissue_of",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="reissues",
                        to="documents.documentissuance",
                    ),
                ),
                (
                    "semester_result",
                    models.ForeignKey(
                        blank=True,
                        null=True,
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="document_issuances",
                        to="results.semesterresult",
                    ),
                ),
                (
                    "source_batch",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.PROTECT,
                        related_name="document_issuances",
                        to="results.resultbatch",
                    ),
                ),
            ],
            options={"ordering": ["-issue_date", "-id"]},
        ),
        migrations.AddIndex(
            model_name="documentinventory",
            index=models.Index(
                fields=["is_active", "start_number"],
                name="doc_inv_active_start_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="bankslip",
            constraint=models.UniqueConstraint(
                fields=("bank", "slip_no_normalized", "deposit_date"),
                name="unique_document_bank_slip",
            ),
        ),
        migrations.AddIndex(
            model_name="bankslip",
            index=models.Index(
                fields=["deposit_date", "slip_no_normalized"],
                name="doc_slip_date_no_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="bankslip",
            index=models.Index(
                fields=["bank", "deposit_date"],
                name="doc_slip_bank_date_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="documentissuance",
            constraint=models.UniqueConstraint(
                fields=("inventory", "serial_number"),
                name="unique_document_inventory_serial",
            ),
        ),
        migrations.AddIndex(
            model_name="documentissuance",
            index=models.Index(
                fields=["document_type", "issue_date"],
                name="doc_issue_type_date_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="documentissuance",
            index=models.Index(
                fields=["enrollment"],
                name="doc_issue_enrollment_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="documentissuance",
            index=models.Index(
                fields=["payment_slip"],
                name="doc_issue_payment_slip_idx",
            ),
        ),
    ]
