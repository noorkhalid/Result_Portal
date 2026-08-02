from __future__ import annotations

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Q
from django.shortcuts import get_object_or_404, redirect, render

from dashboards.access import restrict_department_queryset
from dashboards.decorators import group_required
from documents.forms import (
    BankForm,
    BankSlipForm,
    DocumentInventoryForm,
    DocumentIssuanceForm,
    DocumentReissueForm,
)
from documents.models import Bank, BankSlip, DocumentInventory, DocumentIssuance
from documents.services import create_document_issuance, next_available_serial
from results.dmc_services import evaluate_dmc_eligibility
from results.models import SemesterResult
from results.transcript_services import evaluate_transcript_eligibility
from students.models import Enrollment


ISSUANCE_ROLES = ("System Admin", "Document Generator", "Controller")
INVENTORY_ROLES = ("System Admin", "Controller")
BANK_ROLES = ("System Admin", "Controller")


def _accessible_issuances(user):
    queryset = DocumentIssuance.objects.select_related(
        "inventory",
        "payment_slip",
        "payment_slip__bank",
        "enrollment",
        "enrollment__student",
        "enrollment__department",
        "source_batch",
        "source_batch__exam_type",
        "semester_result",
        "issued_by",
        "reissue_of",
    )
    return restrict_department_queryset(queryset, user, "enrollment__department")


def _form_error_text(exc: ValidationError) -> str:
    if hasattr(exc, "messages") and exc.messages:
        return " ".join(str(value) for value in exc.messages)
    return str(exc)


@group_required(*ISSUANCE_ROLES)
def document_issuance_register(request):
    issuances = _accessible_issuances(request.user)

    query = (request.GET.get("q") or "").strip()
    document_type = (request.GET.get("document_type") or "").strip()
    date_from = (request.GET.get("date_from") or "").strip()
    date_to = (request.GET.get("date_to") or "").strip()

    if query:
        issuances = issuances.filter(
            Q(document_no__icontains=query)
            | Q(payment_slip__bank__name__icontains=query)
            | Q(payment_slip__slip_no__icontains=query)
            | Q(payment_slip__depositor_name__icontains=query)
            | Q(enrollment__roll_no__icontains=query)
            | Q(enrollment__student__registration_no__icontains=query)
            | Q(enrollment__student__name__icontains=query)
            | Q(recipient_name__icontains=query)
        )
    if document_type in DocumentInventory.DocumentType.values:
        issuances = issuances.filter(document_type=document_type)
    if date_from:
        issuances = issuances.filter(issue_date__gte=date_from)
    if date_to:
        issuances = issuances.filter(issue_date__lte=date_to)

    paginator = Paginator(issuances, 30)
    page_obj = paginator.get_page(request.GET.get("page"))
    query_params = request.GET.copy()
    query_params.pop("page", None)
    return render(
        request,
        "dashboards/documents/issuance_register.html",
        {
            "page_obj": page_obj,
            "issuances": page_obj.object_list,
            "query": query,
            "document_type": document_type,
            "date_from": date_from,
            "date_to": date_to,
            "document_types": DocumentInventory.DocumentType.choices,
            "qs_params": query_params.urlencode(),
        },
    )


@group_required(*ISSUANCE_ROLES)
def document_issuance_detail(request, pk):
    issuance = get_object_or_404(_accessible_issuances(request.user), pk=pk)
    history_root = issuance.reissue_of or issuance
    history = list(
        _accessible_issuances(request.user)
        .filter(Q(pk=history_root.pk) | Q(reissue_of=history_root))
        .order_by("created_at", "id")
    )
    return render(
        request,
        "dashboards/documents/issuance_detail.html",
        {"issuance": issuance, "history": history},
    )


@group_required(*INVENTORY_ROLES)
def document_inventory_list(request):
    inventories = DocumentInventory.objects.select_related("created_by").all()
    return render(
        request,
        "dashboards/documents/inventory_list.html",
        {"inventories": inventories},
    )


@group_required(*INVENTORY_ROLES)
def document_inventory_create(request):
    if request.method == "POST":
        form = DocumentInventoryForm(request.POST)
        if form.is_valid():
            inventory = form.save(commit=False)
            inventory.created_by = request.user
            try:
                inventory.save()
            except ValidationError as exc:
                form.add_error(None, _form_error_text(exc))
            else:
                messages.success(request, "Sheet bundle added successfully.")
                return redirect("admin_document_inventory_list")
    else:
        form = DocumentInventoryForm()
    return render(
        request,
        "dashboards/documents/inventory_form.html",
        {"form": form, "title": "Add Sheet Bundle"},
    )


@group_required(*INVENTORY_ROLES)
def document_inventory_update(request, pk):
    inventory = get_object_or_404(DocumentInventory, pk=pk)
    if request.method == "POST":
        form = DocumentInventoryForm(request.POST, instance=inventory)
        if form.is_valid():
            try:
                form.save()
            except ValidationError as exc:
                form.add_error(None, _form_error_text(exc))
            else:
                messages.success(request, "Sheet bundle updated successfully.")
                return redirect("admin_document_inventory_list")
    else:
        form = DocumentInventoryForm(instance=inventory)
    return render(
        request,
        "dashboards/documents/inventory_form.html",
        {
            "form": form,
            "inventory": inventory,
            "title": "Update Sheet Bundle",
        },
    )


@group_required(*BANK_ROLES)
def bank_list(request):
    banks = Bank.objects.select_related("created_by").all()
    return render(request, "dashboards/documents/bank_list.html", {"banks": banks})


@group_required(*BANK_ROLES)
def bank_create(request):
    if request.method == "POST":
        form = BankForm(request.POST)
        if form.is_valid():
            bank = form.save(commit=False)
            bank.created_by = request.user
            try:
                bank.save()
            except ValidationError as exc:
                form.add_error(None, _form_error_text(exc))
            else:
                messages.success(request, "Bank added successfully.")
                return redirect("admin_document_bank_list")
    else:
        form = BankForm()
    return render(
        request,
        "dashboards/documents/bank_form.html",
        {"form": form, "title": "Add Bank"},
    )


@group_required(*BANK_ROLES)
def bank_update(request, pk):
    bank = get_object_or_404(Bank, pk=pk)
    if request.method == "POST":
        form = BankForm(request.POST, instance=bank)
        if form.is_valid():
            try:
                form.save()
            except ValidationError as exc:
                form.add_error(None, _form_error_text(exc))
            else:
                messages.success(request, "Bank updated successfully.")
                return redirect("admin_document_bank_list")
    else:
        form = BankForm(instance=bank)
    return render(
        request,
        "dashboards/documents/bank_form.html",
        {"form": form, "title": "Update Bank", "bank": bank},
    )


@group_required(*ISSUANCE_ROLES)
def bank_slip_list(request):
    slips = BankSlip.objects.select_related("bank", "created_by")
    query = (request.GET.get("q") or "").strip()
    if query:
        slips = slips.filter(
            Q(bank__name__icontains=query)
            | Q(slip_no__icontains=query)
            | Q(depositor_name__icontains=query)
        )
    paginator = Paginator(slips, 30)
    page_obj = paginator.get_page(request.GET.get("page"))
    query_params = request.GET.copy()
    query_params.pop("page", None)
    return render(
        request,
        "dashboards/documents/bank_slip_list.html",
        {
            "page_obj": page_obj,
            "slips": page_obj.object_list,
            "query": query,
            "qs_params": query_params.urlencode(),
        },
    )


@group_required(*ISSUANCE_ROLES)
def bank_slip_create(request):
    if request.method == "POST":
        form = BankSlipForm(request.POST)
        if form.is_valid():
            slip = form.save(commit=False)
            slip.created_by = request.user
            try:
                slip.save()
            except ValidationError as exc:
                form.add_error(None, _form_error_text(exc))
            else:
                messages.success(request, "Bank slip recorded successfully.")
                return redirect("admin_document_bank_slip_detail", pk=slip.pk)
    else:
        form = BankSlipForm()
    return render(
        request,
        "dashboards/documents/bank_slip_form.html",
        {"form": form, "title": "Record Bank Slip"},
    )


@group_required(*ISSUANCE_ROLES)
def bank_slip_update(request, pk):
    slip = get_object_or_404(BankSlip, pk=pk)
    if slip.allocations.exists():
        messages.info(request, "A bank slip cannot be edited after any amount has been allocated.")
        return redirect("admin_document_bank_slip_detail", pk=slip.pk)
    if request.method == "POST":
        form = BankSlipForm(request.POST, instance=slip)
        if form.is_valid():
            try:
                form.save()
            except ValidationError as exc:
                form.add_error(None, _form_error_text(exc))
            else:
                messages.success(request, "Bank slip updated successfully.")
                return redirect("admin_document_bank_slip_detail", pk=slip.pk)
    else:
        form = BankSlipForm(instance=slip)
    return render(
        request,
        "dashboards/documents/bank_slip_form.html",
        {"form": form, "title": "Update Bank Slip", "slip": slip},
    )


@group_required(*ISSUANCE_ROLES)
def bank_slip_detail(request, pk):
    slip = get_object_or_404(
        BankSlip.objects.select_related("bank", "created_by"),
        pk=pk,
    )
    allocations = _accessible_issuances(request.user).filter(payment_slip=slip).order_by("issue_date", "id")
    return render(
        request,
        "dashboards/documents/bank_slip_detail.html",
        {"slip": slip, "allocations": allocations},
    )


def _create_from_form(
    *,
    request,
    form,
    document_type,
    semester_result=None,
    enrollment=None,
    source_batch=None,
    reissue_of=None,
):
    data = form.cleaned_data
    use_existing = data["payment_source"] == DocumentIssuanceForm.PAYMENT_EXISTING
    return create_document_issuance(
        document_type=document_type,
        issued_by=request.user,
        serial_number=data["serial_number"],
        issue_date=data["issue_date"],
        payment_slip=data.get("existing_payment_slip") if use_existing else None,
        bank=None if use_existing else data.get("bank"),
        deposit_type=data.get("deposit_type") or BankSlip.DepositType.CASH_DEPOSIT,
        bank_slip_no=data.get("bank_slip_no", ""),
        bank_slip_date=data.get("bank_slip_date"),
        bank_slip_total_amount=data.get("bank_slip_total_amount"),
        depositor_name=data.get("depositor_name", ""),
        amount_utilized=data["amount_utilized"],
        recipient_name=data["recipient_name"],
        remarks=data.get("remarks", ""),
        semester_result=semester_result,
        enrollment=enrollment,
        source_batch=source_batch,
        reissue_of=reissue_of,
        reissue_reason=data.get("reissue_reason", ""),
    )


def _issuance_form(*args, recipient_name="", **kwargs):
    return DocumentIssuanceForm(
        *args,
        recipient_name=recipient_name,
        suggested_serial=next_available_serial(),
        **kwargs,
    )


def _reissue_form(*args, recipient_name="", **kwargs):
    return DocumentReissueForm(
        *args,
        recipient_name=recipient_name,
        suggested_serial=next_available_serial(),
        **kwargs,
    )


@group_required(*ISSUANCE_ROLES)
def issue_dmc(request, semester_result_id):
    queryset = SemesterResult.objects.select_related(
        "batch",
        "batch__exam_type",
        "enrollment",
        "enrollment__student",
        "enrollment__department",
    )
    queryset = restrict_department_queryset(queryset, request.user, "enrollment__department")
    semester_result = get_object_or_404(queryset, pk=semester_result_id)
    eligibility = evaluate_dmc_eligibility(semester_result)
    if not eligibility.is_eligible:
        messages.error(request, f"DMC cannot be issued: {eligibility.reason}")
        return redirect("admin_dmc_single")

    existing = (
        _accessible_issuances(request.user)
        .filter(
            document_type=DocumentInventory.DocumentType.DMC,
            semester_result=semester_result,
            reissue_of__isnull=True,
        )
        .first()
    )
    if existing:
        messages.info(
            request,
            f'DMC already issued as "{existing.document_no}". Use Reissue from its register entry.',
        )
        return redirect("admin_document_issuance_detail", pk=existing.pk)

    if request.method == "POST":
        form = _issuance_form(request.POST)
        if form.is_valid():
            try:
                issuance = _create_from_form(
                    request=request,
                    form=form,
                    document_type=DocumentInventory.DocumentType.DMC,
                    semester_result=semester_result,
                )
            except ValidationError as exc:
                form.add_error(None, _form_error_text(exc))
            else:
                messages.success(request, f'DMC issued successfully as serial "{issuance.document_no}".')
                return redirect("admin_document_issuance_detail", pk=issuance.pk)
    else:
        form = _issuance_form(recipient_name=semester_result.enrollment.student.name)

    return render(
        request,
        "dashboards/documents/issuance_form.html",
        {
            "form": form,
            "document_type_label": "DMC",
            "semester_result": semester_result,
            "enrollment": semester_result.enrollment,
            "source_batch": semester_result.batch,
            "eligibility": eligibility,
            "has_available_inventory": next_available_serial() is not None,
        },
    )


@group_required(*ISSUANCE_ROLES)
def issue_transcript(request, enrollment_id):
    queryset = Enrollment.objects.select_related(
        "student", "department", "program", "session", "curriculum"
    )
    queryset = restrict_department_queryset(queryset, request.user, "department")
    enrollment = get_object_or_404(queryset, pk=enrollment_id)
    eligibility = evaluate_transcript_eligibility(enrollment)
    if not eligibility.is_eligible:
        messages.error(request, f"Transcript cannot be issued: {eligibility.reason}")
        return redirect("admin_transcript_single")

    semester_end = enrollment.curriculum.semester_end
    final_result = (
        SemesterResult.objects.filter(
            enrollment=enrollment,
            batch__semester_number=semester_end,
        )
        .select_related("batch", "batch__exam_type")
        .order_by("-batch__created_at", "-batch_id", "-id")
        .first()
    )
    if not final_result:
        messages.error(request, "Final-semester result batch is missing.")
        return redirect("admin_transcript_single")

    existing = (
        _accessible_issuances(request.user)
        .filter(
            document_type=DocumentInventory.DocumentType.TRANSCRIPT,
            enrollment=enrollment,
            semester_result__isnull=True,
            reissue_of__isnull=True,
        )
        .first()
    )
    if existing:
        messages.info(
            request,
            f'Transcript already issued as "{existing.document_no}". Use Reissue from its register entry.',
        )
        return redirect("admin_document_issuance_detail", pk=existing.pk)

    if request.method == "POST":
        form = _issuance_form(request.POST)
        if form.is_valid():
            try:
                issuance = _create_from_form(
                    request=request,
                    form=form,
                    document_type=DocumentInventory.DocumentType.TRANSCRIPT,
                    enrollment=enrollment,
                    source_batch=final_result.batch,
                )
            except ValidationError as exc:
                form.add_error(None, _form_error_text(exc))
            else:
                messages.success(request, f'Transcript issued successfully as serial "{issuance.document_no}".')
                return redirect("admin_document_issuance_detail", pk=issuance.pk)
    else:
        form = _issuance_form(recipient_name=enrollment.student.name)

    return render(
        request,
        "dashboards/documents/issuance_form.html",
        {
            "form": form,
            "document_type_label": "Transcript",
            "enrollment": enrollment,
            "source_batch": final_result.batch,
            "eligibility": eligibility,
            "has_available_inventory": next_available_serial() is not None,
        },
    )


@group_required(*ISSUANCE_ROLES)
def reissue_document(request, pk):
    original = get_object_or_404(_accessible_issuances(request.user), pk=pk)
    history_root = original.reissue_of or original

    if request.method == "POST":
        form = _reissue_form(request.POST)
        if form.is_valid():
            try:
                issuance = _create_from_form(
                    request=request,
                    form=form,
                    document_type=original.document_type,
                    semester_result=original.semester_result,
                    enrollment=original.enrollment,
                    source_batch=original.source_batch,
                    reissue_of=history_root,
                )
            except ValidationError as exc:
                form.add_error(None, _form_error_text(exc))
            else:
                messages.success(request, f'Document reissued successfully as serial "{issuance.document_no}".')
                return redirect("admin_document_issuance_detail", pk=issuance.pk)
    else:
        form = _reissue_form(recipient_name=original.enrollment.student.name)

    return render(
        request,
        "dashboards/documents/issuance_form.html",
        {
            "form": form,
            "document_type_label": original.get_document_type_display(),
            "enrollment": original.enrollment,
            "semester_result": original.semester_result,
            "source_batch": original.source_batch,
            "original": history_root,
            "is_reissue": True,
            "has_available_inventory": next_available_serial() is not None,
        },
    )
