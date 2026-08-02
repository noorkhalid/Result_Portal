from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.models import User
from django.shortcuts import redirect

from academics.models import Department
from results.models import ResultBatch, ResultNotification
from students.models import Enrollment

DEALING_ASSISTANT_GROUP = "Dealing Assistant"
CONTROLLER_GROUP = "Controller"
DOCUMENT_GENERATOR_GROUP = "Document Generator"


def _has_group(user, group_name: str) -> bool:
    return bool(
        user.is_authenticated
        and hasattr(user, "groups")
        and user.groups.filter(name=group_name).exists()
    )


def is_system_admin(user) -> bool:
    return bool(
        user.is_authenticated
        and (user.is_superuser or _has_group(user, "System Admin"))
    )


def is_dealing_assistant(user) -> bool:
    return _has_group(user, DEALING_ASSISTANT_GROUP)


def is_controller(user) -> bool:
    return _has_group(user, CONTROLLER_GROUP)


def is_document_generator(user) -> bool:
    return _has_group(user, DOCUMENT_GENERATOR_GROUP)


def can_access_all_departments(user) -> bool:
    """Return whether a role has read access across all departments.

    Controllers and Document Generators need portal-wide read access for official
    document generation, while Dealing Assistants remain limited to their assigned
    departments.
    """

    return bool(
        is_system_admin(user)
        or is_controller(user)
        or is_document_generator(user)
    )


def can_access_documents(user) -> bool:
    return bool(
        can_access_all_departments(user)
        or is_dealing_assistant(user)
    )


def assigned_departments_qs(user):
    if can_access_all_departments(user):
        return Department.objects.all().order_by("name")
    if is_dealing_assistant(user):
        return Department.objects.filter(assigned_assistant=user).order_by("name")
    return Department.objects.none()


def assigned_department_ids(user):
    return list(assigned_departments_qs(user).values_list("id", flat=True))


def user_can_access_department(user, department) -> bool:
    if can_access_all_departments(user):
        return True
    if not is_dealing_assistant(user):
        return False
    return bool(
        department
        and getattr(department, "assigned_assistant_id", None) == user.id
    )


def restrict_department_queryset(queryset, user, field_name: str = "department"):
    if can_access_all_departments(user):
        return queryset
    if is_dealing_assistant(user):
        return queryset.filter(**{f"{field_name}__assigned_assistant": user})
    return queryset.none()


def get_accessible_batch_or_none(user, pk: int):
    qs = ResultBatch.objects.select_related(
        "department", "program", "session", "exam_type", "curriculum"
    )
    qs = restrict_department_queryset(qs, user, "department")
    return qs.filter(pk=pk).first()


def get_accessible_notification_or_none(user, notification_id: int):
    qs = ResultNotification.objects.select_related("batch", "batch__department")
    qs = restrict_department_queryset(qs, user, "batch__department")
    return qs.filter(pk=notification_id).first()


def get_accessible_enrollment_or_none(user, enrollment_id: int):
    qs = Enrollment.objects.select_related(
        "department", "program", "session", "student"
    )
    qs = restrict_department_queryset(qs, user, "department")
    return qs.filter(pk=enrollment_id).first()


def deny_department_access(
    request,
    message: str = "You do not have permission to access that department.",
):
    messages.error(request, message)
    return redirect("dashboard")


def dealing_assistant_users_qs():
    return (
        User.objects.filter(
            groups__name=DEALING_ASSISTANT_GROUP,
            is_active=True,
        )
        .distinct()
        .order_by("username")
    )
