from django.urls import path

# ==================================================
# CORE (ROLE-BASED DASHBOARDS)
# ==================================================
from dashboards.views import core

# ==================================================
# SYSTEM ADMIN — COURSES
# ==================================================
from dashboards.views.course_views import (
    course_list,
    course_create,
    course_update,
    course_delete,
)

# ==================================================
# SYSTEM ADMIN — PROGRAMS
# ==================================================
from academics.views import (
    admin_program_list,
    admin_program_create,
    admin_program_update,
    admin_program_delete,
)

urlpatterns = [

    # ==================================================
    # HOME / MAIN ROUTER
    # ==================================================
    path("", core.home, name="home"),
    path("dashboard/", core.dashboard, name="dashboard"),

    # ==================================================
    # ROLE-BASED DASHBOARDS
    # ==================================================
    path(
        "controller/dashboard/",
        core.controller_dashboard,
        name="dash_controller",
    ),
    path(
        "data-entry/dashboard/",
        core.data_entry_dashboard,
        name="dash_data_entry",
    ),
    path(
        "data-entry/import/",
        core.data_entry_import_marks,
        name="data_entry_import_marks",
    ),
    path(
        "documents/dashboard/",
        core.document_generator_dashboard,
        name="dash_document_generator",
    ),
    path(
        "results/dashboard/",
        core.result_checker_dashboard,
        name="dash_result_checker",
    ),

    # ==================================================
    # SYSTEM ADMIN — MAIN DASHBOARD
    # ==================================================
    path(
        "admin-dashboard/",
        core.system_admin_dashboard,
        name="dash_system_admin",
    ),

    # ==================================================
    # SYSTEM ADMIN — COURSES
    # ==================================================
    path(
        "admin-dashboard/courses/",
        course_list,
        name="admin_course_list",
    ),
    path(
        "admin-dashboard/courses/add/",
        course_create,
        name="admin_course_add",
    ),
    path(
        "admin-dashboard/courses/<int:pk>/edit/",
        course_update,
        name="admin_course_edit",
    ),
    path(
        "admin-dashboard/courses/<int:pk>/delete/",
        course_delete,
        name="admin_course_delete",
    ),

    # ==================================================
    # SYSTEM ADMIN — PROGRAMS
    # ==================================================
    path(
        "admin-dashboard/programs/",
        admin_program_list,
        name="admin_program_list",
    ),
    path(
        "admin-dashboard/programs/add/",
        admin_program_create,
        name="admin_program_add",
    ),
    path(
        "admin-dashboard/programs/<int:pk>/edit/",
        admin_program_update,
        name="admin_program_edit",
    ),
    path(
        "admin-dashboard/programs/<int:pk>/delete/",
        admin_program_delete,
        name="admin_program_delete",
    ),
]
