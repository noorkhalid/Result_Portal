from __future__ import annotations

from django.contrib import messages
from django.contrib.auth.models import User
from django.shortcuts import redirect

from academics.models import Department
from results.models import ResultBatch, ResultNotification
from students.models import Enrollment

DEALING_ASSISTANT_GROUP = "Dealing Assistant"


def is_system_admin(user) -> bool:
    return bool(user.is_authenticated and (user.is_superuser or user.groups.filter(name="System Admin").exists()))


def is_dealing_assistant(user) -> bool:
    return bool(user.is_authenticated and user.groups.filter(name=DEALING_ASSISTANT_GROUP).exists())


def assigned_departments_qs(user):
    if is_system_admin(user):
        return Department.objects.all().order_by("name")
    if is_dealing_assistant(user):
        return Department.objects.filter(assigned_assistant=user).order_by("name")
    return Department.objects.none()


def assigned_department_ids(user):
    return list(assigned_departments_qs(user).values_list("id", flat=True))


def user_can_access_department(user, department) -> bool:
    if is_system_admin(user):
        return True
    if not is_dealing_assistant(user):
        return False
    return bool(department and getattr(department, "assigned_assistant_id", None) == user.id)


def restrict_department_queryset(queryset, user, field_name: str = "department"):
    if is_system_admin(user):
        return queryset
    if is_dealing_assistant(user):
        return queryset.filter(**{f"{field_name}__assigned_assistant": user})
    return queryset.none()


def get_accessible_batch_or_none(user, pk: int):
    qs = ResultBatch.objects.select_related("department", "program", "session", "exam_type", "curriculum")
    qs = restrict_department_queryset(qs, user, "department")
    return qs.filter(pk=pk).first()


def get_accessible_notification_or_none(user, notification_id: int):
    qs = ResultNotification.objects.select_related("batch", "batch__department")
    if is_system_admin(user):
        return qs.filter(pk=notification_id).first()
    if is_dealing_assistant(user):
        return qs.filter(pk=notification_id, batch__department__assigned_assistant=user).first()
    return None


def get_accessible_enrollment_or_none(user, enrollment_id: int):
    qs = Enrollment.objects.select_related("department", "program", "session", "student")
    qs = restrict_department_queryset(qs, user, "department")
    return qs.filter(pk=enrollment_id).first()


def deny_department_access(request, message: str = "You do not have permission to access that department."):
    messages.error(request, message)
    return redirect("dashboard")


def dealing_assistant_users_qs():
    return User.objects.filter(groups__name=DEALING_ASSISTANT_GROUP, is_active=True).distinct().order_by("username")
