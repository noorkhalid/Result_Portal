from django.contrib import messages
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render

from dashboards.decorators import group_required
from results.models import HoldCategory


def _first_validation_message(exc: ValidationError) -> str:
    if hasattr(exc, "message_dict"):
        messages_list = []
        for values in exc.message_dict.values():
            messages_list.extend(values)
        if messages_list:
            return " ".join(messages_list)
    if hasattr(exc, "messages") and exc.messages:
        return " ".join(exc.messages)
    return str(exc)


@group_required("System Admin")
def hold_category_list(request):
    categories = HoldCategory.objects.all().order_by("sort_order", "name")
    return render(
        request,
        "dashboards/hold_categories/list.html",
        {"categories": categories},
    )


@group_required("System Admin")
def hold_category_create(request):
    if request.method == "POST":
        category = HoldCategory(
            code=(request.POST.get("code") or "").strip().lower(),
            name=(request.POST.get("name") or "").strip(),
            is_active=bool(request.POST.get("is_active")),
            sort_order=request.POST.get("sort_order") or 0,
        )
        try:
            category.save()
            messages.success(request, "Hold category created successfully.")
            return redirect("admin_hold_category_list")
        except ValidationError as exc:
            messages.error(request, _first_validation_message(exc))
        except IntegrityError:
            messages.error(request, "A hold category with this code or name already exists.")
    else:
        category = HoldCategory(is_active=True)

    return render(
        request,
        "dashboards/hold_categories/form.html",
        {"title": "Add Hold Category", "category": category},
    )


@group_required("System Admin")
def hold_category_update(request, pk):
    category = get_object_or_404(HoldCategory, pk=pk)

    if request.method == "POST":
        category.code = (request.POST.get("code") or "").strip().lower()
        category.name = (request.POST.get("name") or "").strip()
        category.is_active = bool(request.POST.get("is_active"))
        category.sort_order = request.POST.get("sort_order") or 0
        try:
            category.save()
            messages.success(request, "Hold category updated successfully.")
            return redirect("admin_hold_category_list")
        except ValidationError as exc:
            messages.error(request, _first_validation_message(exc))
        except IntegrityError:
            messages.error(request, "A hold category with this code or name already exists.")

    return render(
        request,
        "dashboards/hold_categories/form.html",
        {"title": "Edit Hold Category", "category": category},
    )


@group_required("System Admin")
def hold_category_delete(request, pk):
    category = get_object_or_404(HoldCategory, pk=pk)
    delete_blocked = category.is_in_use

    if request.method == "POST":
        if delete_blocked:
            messages.error(
                request,
                "Cannot delete: this hold category is already used. Deactivate it instead.",
            )
            return redirect("admin_hold_category_list")
        category.delete()
        messages.success(request, "Hold category deleted successfully.")
        return redirect("admin_hold_category_list")

    return render(
        request,
        "dashboards/hold_categories/confirm_delete.html",
        {"category": category, "delete_blocked": delete_blocked},
    )
