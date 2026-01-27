from django.urls import path

from dashboards.views import core
from dashboards.views import import_views


from dashboards.views.course_views import (
    course_list,
    course_create,
    course_update,
    course_delete,
)

from academics.views import (
    admin_program_list,
    admin_program_create,
    admin_program_update,
    admin_program_delete,
)

from dashboards.views.session_views import (
    session_list,
    session_create,
    session_update,
    session_delete,
)

from dashboards.views.semester_views import (
    semester_list,
    semester_create,
    semester_update,
    semester_delete,
)

from dashboards.views.program_course_views import (
    program_course_list,
    program_course_create,
    program_course_update,
    program_course_delete,
)

from dashboards.views.student_views import (
    student_list,
    student_create,
    student_update,
    student_delete,
)

from dashboards.views.enrollment_views import (
    enrollment_list,
    enrollment_create,
    enrollment_update,
    enrollment_delete,
)

from dashboards.views.grade_scale_views import (
    grade_scale_list,
    grade_scale_create,
    grade_scale_update,
    grade_scale_delete,
)

from dashboards.views.result_batch_views import (
    batch_list,
    batch_create,
    batch_update,
    batch_delete,
)

from dashboards.views.department_views import (
    set_active_department,
    department_list,
    department_create,
    department_update,
    department_delete,
)

from dashboards.views.result_notification_views import (
    result_notifications,
)

urlpatterns = [
    # Home / router
    path("", core.home, name="home"),
    path("dashboard/", core.dashboard, name="dashboard"),

    # Role dashboards
    path("controller/dashboard/", core.controller_dashboard, name="dash_controller"),
    path("data-entry/dashboard/", core.data_entry_dashboard, name="dash_data_entry"),
    path("data-entry/import/", core.data_entry_import_marks, name="data_entry_import_marks"),
    path("data-entry/import/template/", core.data_entry_marks_template, name="data_entry_marks_template"),
    path("documents/dashboard/", core.document_generator_dashboard, name="dash_document_generator"),
    path("results/dashboard/", core.result_checker_dashboard, name="dash_result_checker"),

    # System Admin dashboard
    path("admin-dashboard/", core.system_admin_dashboard, name="dash_system_admin"),

    # System Admin — Academics
    path("admin-dashboard/set-department/", set_active_department, name="set_active_department"),

    path("admin-dashboard/departments/", department_list, name="admin_department_list"),
    path("admin-dashboard/departments/add/", department_create, name="admin_department_add"),
    path("admin-dashboard/departments/<int:pk>/edit/", department_update, name="admin_department_edit"),
    path("admin-dashboard/departments/<int:pk>/delete/", department_delete, name="admin_department_delete"),

    path("admin-dashboard/programs/", admin_program_list, name="admin_program_list"),
    path("admin-dashboard/programs/add/", admin_program_create, name="admin_program_add"),
    path("admin-dashboard/programs/<int:pk>/edit/", admin_program_update, name="admin_program_edit"),
    path("admin-dashboard/programs/<int:pk>/delete/", admin_program_delete, name="admin_program_delete"),

    path("admin-dashboard/courses/", course_list, name="admin_course_list"),
    path("admin-dashboard/courses/add/", course_create, name="admin_course_add"),
    path("admin-dashboard/courses/<int:pk>/edit/", course_update, name="admin_course_edit"),
    path("admin-dashboard/courses/<int:pk>/delete/", course_delete, name="admin_course_delete"),

    # System Admin — Excel Imports
    path("admin-dashboard/courses/import/", import_views.import_courses, name="admin_import_courses"),
    path("admin-dashboard/courses/template/", import_views.template_courses, name="admin_template_courses"),

    path("admin-dashboard/students/import/", import_views.import_students, name="admin_import_students"),
    path("admin-dashboard/students/template/", import_views.template_students, name="admin_template_students"),

    path("admin-dashboard/enrollments/import/", import_views.import_enrollments, name="admin_import_enrollments"),
    path("admin-dashboard/enrollments/template/", import_views.template_enrollments, name="admin_template_enrollments"),

    path("admin-dashboard/program-courses/import/", import_views.import_program_courses, name="admin_import_program_courses"),
    path("admin-dashboard/program-courses/template/", import_views.template_program_courses, name="admin_template_program_courses"),

    path("admin-dashboard/program-courses/", program_course_list, name="admin_program_course_list"),
    path("admin-dashboard/program-courses/add/", program_course_create, name="admin_program_course_add"),
    path("admin-dashboard/program-courses/<int:pk>/edit/", program_course_update, name="admin_program_course_edit"),
    path("admin-dashboard/program-courses/<int:pk>/delete/", program_course_delete, name="admin_program_course_delete"),

    path("admin-dashboard/sessions/", session_list, name="admin_session_list"),
    path("admin-dashboard/sessions/add/", session_create, name="admin_session_add"),
    path("admin-dashboard/sessions/<int:pk>/edit/", session_update, name="admin_session_edit"),
    path("admin-dashboard/sessions/<int:pk>/delete/", session_delete, name="admin_session_delete"),

    path("admin-dashboard/semesters/", semester_list, name="admin_semester_list"),
    path("admin-dashboard/semesters/add/", semester_create, name="admin_semester_add"),
    path("admin-dashboard/semesters/<int:pk>/edit/", semester_update, name="admin_semester_edit"),
    path("admin-dashboard/semesters/<int:pk>/delete/", semester_delete, name="admin_semester_delete"),

    # System Admin — Students
    path("admin-dashboard/students/", student_list, name="admin_student_list"),
    path("admin-dashboard/students/add/", student_create, name="admin_student_add"),
    path("admin-dashboard/students/<int:pk>/edit/", student_update, name="admin_student_edit"),
    path("admin-dashboard/students/<int:pk>/delete/", student_delete, name="admin_student_delete"),

    path("admin-dashboard/enrollments/", enrollment_list, name="admin_enrollment_list"),
    path("admin-dashboard/enrollments/add/", enrollment_create, name="admin_enrollment_add"),
    path("admin-dashboard/enrollments/<int:pk>/edit/", enrollment_update, name="admin_enrollment_edit"),
    path("admin-dashboard/enrollments/<int:pk>/delete/", enrollment_delete, name="admin_enrollment_delete"),

    # System Admin — Results
    path("admin-dashboard/result-batches/", batch_list, name="admin_batch_list"),
    path("admin-dashboard/result-batches/add/", batch_create, name="admin_batch_add"),
    path("admin-dashboard/result-batches/<int:pk>/edit/", batch_update, name="admin_batch_edit"),
    path("admin-dashboard/result-batches/<int:pk>/delete/", batch_delete, name="admin_batch_delete"),

    path("admin-dashboard/grade-scales/", grade_scale_list, name="admin_grade_scale_list"),
    path("admin-dashboard/grade-scales/add/", grade_scale_create, name="admin_grade_scale_add"),
    path("admin-dashboard/grade-scales/<int:pk>/edit/", grade_scale_update, name="admin_grade_scale_edit"),
    path("admin-dashboard/grade-scales/<int:pk>/delete/", grade_scale_delete, name="admin_grade_scale_delete"),

    # System Admin — Documents
    path(
        "admin-dashboard/documents/result-notifications/",
        result_notifications,
        name="admin_result_notifications",
    ),
]
