from functools import wraps

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect


def group_required(*group_names: str):
    """Require that the logged-in user belongs to at least one of the given groups.

    Superusers always pass.
    """

    def decorator(view_func):
        @login_required
        @wraps(view_func)
        def _wrapped(request, *args, **kwargs):
            user = request.user
            if user.is_superuser:
                return view_func(request, *args, **kwargs)

            if not group_names:
                return view_func(request, *args, **kwargs)

            if user.groups.filter(name__in=group_names).exists():
                return view_func(request, *args, **kwargs)

            messages.error(request, "You do not have permission to access that page.")
            return redirect("dashboard")

        return _wrapped

    return decorator
