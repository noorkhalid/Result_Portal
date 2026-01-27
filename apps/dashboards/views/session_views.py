from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render

from academics.models import Session
from dashboards.decorators import group_required
from dashboards.forms import SessionForm


@group_required("System Admin")
def session_list(request):
    sessions = Session.objects.all().order_by("-start_year")
    return render(request, "dashboards/sessions/list.html", {"sessions": sessions})


@group_required("System Admin")
def session_create(request):
    if request.method == "POST":
        form = SessionForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Session created successfully.")
            return redirect("admin_session_list")
    else:
        form = SessionForm()

    return render(
        request,
        "dashboards/sessions/form.html",
        {"form": form, "title": "Add Session"},
    )


@group_required("System Admin")
def session_update(request, pk):
    session = get_object_or_404(Session, pk=pk)

    if request.method == "POST":
        form = SessionForm(request.POST, instance=session)
        if form.is_valid():
            form.save()
            messages.success(request, "Session updated successfully.")
            return redirect("admin_session_list")
    else:
        form = SessionForm(instance=session)

    return render(
        request,
        "dashboards/sessions/form.html",
        {"form": form, "title": "Edit Session", "session": session},
    )


@group_required("System Admin")
def session_delete(request, pk):
    session = get_object_or_404(Session, pk=pk)

    # Prevent delete if linked enrollments/batches exist
    delete_blocked = (
        session.enrollment_set.exists()
        or session.resultbatch_set.exists()
        or session.semester_set.exists()
    )

    if request.method == "POST":
        if delete_blocked:
            messages.error(request, "Cannot delete: this session is in use.")
            return redirect("admin_session_list")

        session.delete()
        messages.success(request, "Session deleted successfully.")
        return redirect("admin_session_list")

    return render(
        request,
        "dashboards/sessions/confirm_delete.html",
        {"session": session, "delete_blocked": delete_blocked},
    )
