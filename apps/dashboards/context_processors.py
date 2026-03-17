from __future__ import annotations

from academics.models import Department, get_default_department
from dashboards.access import assigned_departments_qs, is_dealing_assistant, is_system_admin


def get_active_department(request):
    """Return active department from session (create default if missing)."""
    dept_id = request.session.get("active_department_id")
    dept = None
    if dept_id:
        dept = Department.objects.filter(id=dept_id).first()
    if dept is None:
        dept = get_default_department()
        request.session["active_department_id"] = dept.id
    return dept


def role_flags(request):
    user = request.user

    is_admin = is_system_admin(user)
    is_assistant = is_dealing_assistant(user)

    ctx = {
        "is_system_admin": is_admin,
        "is_dealing_assistant": is_assistant,
        "can_manage_results": is_admin or is_assistant,
        "can_delete_results": is_admin,
    }

    if user.is_authenticated:
        if is_admin or is_assistant:
            departments = assigned_departments_qs(user)
        else:
            departments = Department.objects.all().order_by("name")

        active_department = get_active_department(request)
        if is_assistant and active_department and active_department.assigned_assistant_id != user.id:
            active_department = departments.first()
            if active_department:
                request.session["active_department_id"] = active_department.id

        ctx.update(
            {
                "departments": departments,
                "active_department": active_department,
            }
        )

    return ctx
