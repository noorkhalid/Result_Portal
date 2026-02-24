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


from dashboards.views.curriculum_views import (
    curriculum_designer,
    curriculum_course_add,
    curriculum_course_delete,
    curriculum_copy_previous,
)

from dashboards.views.program_offering_views import (
    program_offering_list,
    program_offering_create,
    program_offering_update,
    program_offering_delete,
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
    enrollment_detail,
    enrollment_delete_marks_from_batch,
)

from dashboards.views.grade_scale_views import (
    grade_scale_list,
    grade_scale_create,
    grade_scale_update,
    grade_scale_delete,
)

from dashboards.views.exam_type_views import (
    exam_type_list,
    exam_type_create,
    exam_type_update,
    exam_type_delete,
)

from dashboards.views.result_batch_views import (
    batch_list,
    batch_create,
    batch_update,
    batch_delete,
    batch_detail,
    batch_students_holds,
    batch_notifications,
    batch_notification_delete,
    batch_recompute,
)

from dashboards.views.marks_entry_views import (
    batch_marks_select_course,
    batch_marks_entry,
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

from dashboards.views.dmc_views import (
    dmc_single,
)

from dashboards.views.transcript_views import (
    transcript_single,
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

    path("admin-dashboard/program-offerings/", program_offering_list, name="admin_program_offering_list"),
    path("admin-dashboard/program-offerings/add/", program_offering_create, name="admin_program_offering_add"),
    path("admin-dashboard/program-offerings/<int:pk>/edit/", program_offering_update, name="admin_program_offering_edit"),
    path("admin-dashboard/program-offerings/<int:pk>/delete/", program_offering_delete, name="admin_program_offering_delete"),

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

    # System Admin — Curriculum (by Session) — the ONLY curriculum source in v4
    path(
        "admin-dashboard/curricula/",
        curriculum_designer,
        name="admin_curriculum_designer",
    ),
    path(
        "admin-dashboard/curricula/add/",
        curriculum_course_add,
        name="admin_curriculum_course_add",
    ),
    path(
        "admin-dashboard/curricula/<int:pk>/delete/",
        curriculum_course_delete,
        name="admin_curriculum_course_delete",
    ),
    path(
        "admin-dashboard/curricula/copy-previous/",
        curriculum_copy_previous,
        name="admin_curriculum_copy_previous",
    ),

    path("admin-dashboard/sessions/", session_list, name="admin_session_list"),
    path("admin-dashboard/sessions/add/", session_create, name="admin_session_add"),
    path("admin-dashboard/sessions/<int:pk>/edit/", session_update, name="admin_session_edit"),
    path("admin-dashboard/sessions/<int:pk>/delete/", session_delete, name="admin_session_delete"),

    # Semesters CRUD removed: semester numbers come from Program.total_semesters

    # System Admin — Students
    path("admin-dashboard/students/", student_list, name="admin_student_list"),
    path("admin-dashboard/students/add/", student_create, name="admin_student_add"),
    path("admin-dashboard/students/<int:pk>/edit/", student_update, name="admin_student_edit"),
    path("admin-dashboard/students/<int:pk>/delete/", student_delete, name="admin_student_delete"),

    path("admin-dashboard/enrollments/", enrollment_list, name="admin_enrollment_list"),
    path("admin-dashboard/enrollments/add/", enrollment_create, name="admin_enrollment_add"),
    path("admin-dashboard/enrollments/<int:pk>/", enrollment_detail, name="admin_enrollment_detail"),
    path("admin-dashboard/enrollments/<int:pk>/edit/", enrollment_update, name="admin_enrollment_edit"),
    path("admin-dashboard/enrollments/<int:pk>/delete/", enrollment_delete, name="admin_enrollment_delete"),

    path(
        "admin-dashboard/enrollments/<int:enrollment_id>/batches/<int:batch_id>/delete-marks/",
        enrollment_delete_marks_from_batch,
        name="admin_enrollment_delete_marks_from_batch",
    ),

    # System Admin — Results
    path("admin-dashboard/result-batches/", batch_list, name="admin_batch_list"),
    path("admin-dashboard/result-batches/add/", batch_create, name="admin_batch_add"),
    path("admin-dashboard/result-batches/<int:pk>/edit/", batch_update, name="admin_batch_edit"),
    path("admin-dashboard/result-batches/<int:pk>/", batch_detail, name="admin_batch_detail"),

    # Manual marks entry (per batch -> per course)
    path(
        "admin-dashboard/result-batches/<int:pk>/marks/",
        batch_marks_select_course,
        name="admin_batch_marks_select_course",
    ),
    path(
        "admin-dashboard/result-batches/<int:pk>/marks/<int:course_id>/",
        batch_marks_entry,
        name="admin_batch_marks_entry",
    ),

    path(
        "admin-dashboard/result-batches/<int:pk>/students/",
        batch_students_holds,
        name="admin_batch_students_holds",
    ),
    path(
        "admin-dashboard/result-batches/<int:pk>/notifications/",
        batch_notifications,
        name="admin_batch_notifications",
    ),

    path(
        "admin-dashboard/result-batches/<int:pk>/notifications/<int:notification_id>/delete/",
        batch_notification_delete,
        name="admin_batch_notification_delete",
    ),

    path(
        "admin-dashboard/result-batches/<int:pk>/recompute/",
        batch_recompute,
        name="admin_batch_recompute",
    ),

    path("admin-dashboard/result-batches/<int:pk>/delete/", batch_delete, name="admin_batch_delete"),

    path("admin-dashboard/grade-scales/", grade_scale_list, name="admin_grade_scale_list"),
    path("admin-dashboard/grade-scales/add/", grade_scale_create, name="admin_grade_scale_add"),
    path("admin-dashboard/grade-scales/<int:pk>/edit/", grade_scale_update, name="admin_grade_scale_edit"),
    path("admin-dashboard/grade-scales/<int:pk>/delete/", grade_scale_delete, name="admin_grade_scale_delete"),

    path("admin-dashboard/exam-types/", exam_type_list, name="admin_exam_type_list"),
    path("admin-dashboard/exam-types/add/", exam_type_create, name="admin_exam_type_add"),
    path("admin-dashboard/exam-types/<int:pk>/edit/", exam_type_update, name="admin_exam_type_edit"),
    path("admin-dashboard/exam-types/<int:pk>/delete/", exam_type_delete, name="admin_exam_type_delete"),

    # System Admin — Documents
    path(
        "admin-dashboard/documents/result-notifications/",
        result_notifications,
        name="admin_result_notifications",
    ),

    path(
        "admin-dashboard/documents/dmc-single/",
        dmc_single,
        name="admin_dmc_single",
    ),

    path(
        "admin-dashboard/documents/transcript-single/",
        transcript_single,
        name="admin_transcript_single",
    ),
]
