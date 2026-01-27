from __future__ import annotations

from academics.models import Department, get_default_department


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

    is_system_admin = (
        user.is_authenticated
        and (user.is_superuser or user.groups.filter(name="System Admin").exists())
    )

    ctx = {"is_system_admin": is_system_admin}

    # Department context is only needed for authenticated users
    if user.is_authenticated:
        active_department = get_active_department(request)
        ctx.update(
            {
                "departments": Department.objects.all().order_by("name"),
                "active_department": active_department,
            }
        )

    return ctx
