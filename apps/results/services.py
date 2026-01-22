from decimal import Decimal, ROUND_HALF_UP

from results.models import GradeScale, CourseResult, SemesterResult, ResultBatch

Q2 = Decimal("0.01")


def q2(x) -> Decimal:
    return Decimal(str(x)).quantize(Q2, rounding=ROUND_HALF_UP)


def calc_percentage(marks_obtained, max_marks) -> Decimal:
    marks_obtained = Decimal(str(marks_obtained))
    max_marks = Decimal(str(max_marks))
    if max_marks <= 0:
        return Decimal("0.00")
    return q2((marks_obtained / max_marks) * 100)


def find_grade(percentage: Decimal):
    """
    Returns (letter_grade, grade_point, remarks, is_fail)
    Based on GradeScale table.
    """
    percentage = Decimal(str(percentage))

    row = (
        GradeScale.objects.filter(
            min_percentage__lte=percentage,
            max_percentage__gte=percentage,
        )
        .order_by("-min_percentage")
        .first()
    )

    if not row:
        return ("N/A", Decimal("0.00"), "No grade scale", True)

    return (
        row.letter_grade,
        Decimal(str(row.grade_point)),
        row.remarks,
        bool(row.is_fail),
    )


def recompute_batch(batch: ResultBatch):
    """
    1) Compute CourseResult: percentage + letter_grade + grade_point
    2) Compute SemesterResult:
        - semester_total_obtained, semester_total_max
        - semester_percentage
        - semester letter_grade + remarks (from GradeScale using semester_percentage)
        - GPA (weighted by credit hours)
        - subjects_to_reappear (if any course has grade_point == 0 OR scale is_fail)
        - CGPA (weighted across all semesters in same program+session)
    """
    # -----------------------------
    # 1) Update course results
    # -----------------------------
    course_results = CourseResult.objects.filter(batch=batch).select_related("course")

    for cr in course_results:
        pct = calc_percentage(cr.marks_obtained, cr.max_marks)
        letter, gp, rem, is_fail = find_grade(pct)

        cr.percentage = pct
        cr.letter_grade = letter
        cr.grade_point = gp
        cr.save(update_fields=["percentage", "letter_grade", "grade_point"])

    # -----------------------------
    # 2) Semester results per enrollment
    # -----------------------------
    enrollment_ids = (
        CourseResult.objects.filter(batch=batch)
        .values_list("enrollment_id", flat=True)
        .distinct()
    )

    for enrollment_id in enrollment_ids:
        qs = (
            CourseResult.objects.filter(batch=batch, enrollment_id=enrollment_id)
            .select_related("course")
        )

        total_ch = Decimal("0.00")
        total_points = Decimal("0.00")

        sem_obt = Decimal("0.00")
        sem_max = Decimal("0.00")

        fails = []

        for cr in qs:
            ch = Decimal(str(cr.course.credit_hours))
            total_ch += ch
            total_points += (Decimal(str(cr.grade_point)) * ch)

            sem_obt += Decimal(str(cr.marks_obtained))
            sem_max += Decimal(str(cr.max_marks))

            # fail detection: by grading scale OR grade_point == 0
            _, _, _, is_fail = find_grade(Decimal(str(cr.percentage)))
            if is_fail or Decimal(str(cr.grade_point)) == 0:
                fails.append(f"{cr.course.code} - {cr.course.title}")

        gpa = Decimal("0.00")
        if total_ch > 0:
            gpa = q2(total_points / total_ch)

        # Semester % and grade/remarks from grading table
        sem_pct = calc_percentage(sem_obt, sem_max)
        sem_letter, _, sem_remark, sem_is_fail = find_grade(sem_pct)

        # If any subject failed, force overall semester as Fail
        if fails:
            sem_remark = "Fail"
            sem_letter = "F"

        subj_reappear = ", ".join(fails)

        sem_obj, _ = SemesterResult.objects.get_or_create(
            batch=batch,
            enrollment_id=enrollment_id,
        )
        sem_obj.total_obtained = q2(sem_obt)
        sem_obj.total_max = q2(sem_max)
        sem_obj.percentage = sem_pct

        sem_obj.gpa = gpa
        sem_obj.letter_grade = sem_letter
        sem_obj.remarks = sem_remark
        sem_obj.subjects_to_reappear = subj_reappear

        sem_obj.save(
            update_fields=[
                "total_obtained",
                "total_max",
                "percentage",
                "gpa",
                "letter_grade",
                "remarks",
                "subjects_to_reappear",
            ]
        )

        # -----------------------------
        # 3) CGPA (across all semesters in same program+session)
        # -----------------------------
        all_results = CourseResult.objects.filter(
            batch__program=batch.program,
            batch__session=batch.session,
            enrollment_id=enrollment_id,
        ).select_related("course")

        all_ch = Decimal("0.00")
        all_points = Decimal("0.00")

        for cr in all_results:
            ch = Decimal(str(cr.course.credit_hours))
            all_ch += ch
            all_points += (Decimal(str(cr.grade_point)) * ch)

        cgpa = Decimal("0.00")
        if all_ch > 0:
            cgpa = q2(all_points / all_ch)

        sem_obj.cgpa = cgpa
        sem_obj.save(update_fields=["cgpa"])
