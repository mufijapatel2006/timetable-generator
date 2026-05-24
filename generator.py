import random
from collections import defaultdict

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]

PERIODS = 6

# =========================================================
# PRACTICAL SLOT PAIRS
# =========================================================

PRACTICAL_SLOTS = [
    (0, 1),
    (2, 3),
    (4, 5)
]


# =========================================================
# MAIN FUNCTION
# =========================================================

def generate_timetable(db):

    cursor = db.cursor(dictionary=True)

    # =====================================================
    # LOAD DATABASE
    # =====================================================

    cursor.execute("SELECT * FROM classes")
    classes = cursor.fetchall()

    cursor.execute("""
        SELECT
            subjects.*,
            faculty.name AS faculty_name
        FROM subjects
        JOIN faculty
        ON subjects.faculty_id = faculty.id
    """)
    subjects = cursor.fetchall()

    cursor.execute("SELECT * FROM rooms")
    rooms = cursor.fetchall()

    # =====================================================
    # ROOM SEPARATION
    # =====================================================

    classrooms = [
        r for r in rooms
        if r['type'] == 'Classroom'
    ]

    labs = [
        r for r in rooms
        if r['type'] == 'Lab'
    ]

    # =====================================================
    # EMPTY TIMETABLE
    # =====================================================

    timetable = {}

    for cls in classes:

        cname = cls['name'].strip()

        timetable[cname] = [
            [None for _ in range(PERIODS)]
            for _ in range(5)
        ]

    # =====================================================
    # TRACKERS
    # =====================================================

    faculty_busy = set()

    room_busy = set()

    # =====================================================
    # GROUP SUBJECTS
    # =====================================================

    class_theory = defaultdict(list)

    class_practical = defaultdict(list)

    for sub in subjects:

        if sub['type'] == "Theory":

            class_theory[
                sub['class_id']
            ].append(sub)

        else:

            class_practical[
                sub['class_id']
            ].append(sub)

    # =====================================================
    # PRACTICAL ALLOCATION
    # SLOT-BASED BALANCED SCHEDULING
    # =====================================================

    PRACTICAL_SLOTS = [
        (0, 1),
        (2, 3),
        (4, 5)
    ]

    # practical count tracker
    class_practical_done = defaultdict(int)

    # max practicals/week for each class
    class_practical_limit = {}

    for cls in classes:

        cid = cls['id']

        class_practical_limit[cid] = len(
            class_practical[cid]
        )

    # =====================================================
    # ALLOCATE DAY → SLOT → CLASS
    # =====================================================

    for day in range(5):

        for slot_index, (p1, p2) in enumerate(PRACTICAL_SLOTS):

            # shuffle classes for fairness
            random.shuffle(classes)

            for cls in classes:

                cname = cls['name'].strip()

                cid = cls['id']

                tt = timetable[cname]

                practicals = class_practical[cid]

                # no practical subjects
                if len(practicals) == 0:
                    continue

                # already completed weekly practicals
                if (
                    class_practical_done[cid]
                    >= class_practical_limit[cid]
                ):
                    continue

                # already occupied
                if tt[day][p1] is not None:
                    continue

                if tt[day][p2] is not None:
                    continue

                allocation = []

                used_labs = set()

                valid = True

                # =====================================
                # ALLOCATE 4 BATCHES
                # =====================================

                for batch_no in range(4):

                    sub = practicals[
                        (
                            class_practical_done[cid]
                            + batch_no
                        )
                        % len(practicals)
                    ]

                    faculty_id = sub['faculty_id']

                    # faculty clash
                    if (
                        (faculty_id, day, p1)
                        in faculty_busy
                        or
                        (faculty_id, day, p2)
                        in faculty_busy
                    ):

                        valid = False
                        break

                    # find free lab
                    selected_lab = None

                    for lab in labs:

                        if lab['id'] in used_labs:
                            continue

                        if (
                            (lab['id'], day, p1)
                            in room_busy
                            or
                            (lab['id'], day, p2)
                            in room_busy
                        ):
                            continue

                        selected_lab = lab

                        used_labs.add(
                            lab['id']
                        )

                        break

                    if selected_lab is None:

                        valid = False
                        break

                    batch = f"A{batch_no+1}"

                    line = (
                        f"{sub['name']} "
                        f"({sub['faculty_name']}) "
                        f"[{selected_lab['name']}] "
                        f"- {batch}"
                    )

                    allocation.append(
                        (
                            line,
                            faculty_id,
                            selected_lab['id']
                        )
                    )

                # =====================================
                # FINAL INSERT
                # =====================================

                if valid:

                    tt[day][p1] = "<br>".join(
                        [x[0] for x in allocation]
                    )

                    tt[day][p2] = "CONT"

                    # mark busy
                    for _, faculty_id, room_id in allocation:

                        faculty_busy.add(
                            (faculty_id, day, p1)
                        )

                        faculty_busy.add(
                            (faculty_id, day, p2)
                        )

                        room_busy.add(
                            (room_id, day, p1)
                        )

                        room_busy.add(
                            (room_id, day, p2)
                        )

                    class_practical_done[cid] += 1

    # =====================================================
    # THEORY ALLOCATION
    # =====================================================

    remaining_hours = {}

    for sub in subjects:

        if sub['type'] == "Theory":

            remaining_hours[
                sub['id']
            ] = sub['hours']

    # -----------------------------------------------------
    # FILL TIMETABLE
    # -----------------------------------------------------

    for round_no in range(10):

        for day in range(5):

            for period in range(PERIODS):

                for cls in classes:

                    cname = cls['name'].strip()

                    cid = cls['id']

                    tt = timetable[cname]

                    # already occupied
                    if tt[day][period] is not None:
                        continue

                    theories = class_theory[cid]

                    # sort by remaining hours
                    theories = sorted(
                        theories,
                        key=lambda x:
                        remaining_hours[x['id']],
                        reverse=True
                    )

                    allocated = False

                    for sub in theories:

                        if (
                            remaining_hours[
                                sub['id']
                            ] <= 0
                        ):
                            continue

                        faculty_id = sub['faculty_id']

                        # faculty clash
                        if (
                            faculty_id,
                            day,
                            period
                        ) in faculty_busy:
                            continue

                        # max 2 lectures/day
                        same_count = 0

                        for cell in tt[day]:

                            if (
                                cell is not None
                                and
                                sub['name']
                                in str(cell)
                            ):
                                same_count += 1

                        if same_count >= 2:
                            continue

                        # ---------------------------------
                        # FIND FREE CLASSROOM
                        # ---------------------------------

                        selected_room = None

                        for room in classrooms:

                            if (
                                room['id'],
                                day,
                                period
                            ) in room_busy:
                                continue

                            selected_room = room
                            break

                        if selected_room is None:
                            continue

                        # ---------------------------------
                        # FINAL THEORY INSERT
                        # ---------------------------------

                        tt[day][period] = (
                            f"{sub['name']} "
                            f"({sub['faculty_name']}) "
                            f"[{selected_room['name']}]"
                        )

                        faculty_busy.add(
                            (faculty_id, day, period)
                        )

                        room_busy.add(
                            (selected_room['id'], day, period)
                        )

                        remaining_hours[
                            sub['id']
                        ] -= 1

                        allocated = True

                        break

    # =====================================================
    # BACKUP FILLER
    # =====================================================

    for cls in classes:

        cname = cls['name'].strip()

        cid = cls['id']

        tt = timetable[cname]

        theories = class_theory[cid]

        for day in range(5):

            for period in range(PERIODS):

                if tt[day][period] is not None:
                    continue

                filled = False

                for sub in theories:

                    faculty_id = sub['faculty_id']

                    # faculty clash
                    if (
                        faculty_id,
                        day,
                        period
                    ) in faculty_busy:
                        continue

                    selected_room = None

                    for room in classrooms:

                        if (
                            room['id'],
                            day,
                            period
                        ) in room_busy:
                            continue

                        selected_room = room
                        break

                    if selected_room is None:
                        continue

                    tt[day][period] = (
                        f"{sub['name']} "
                        f"({sub['faculty_name']}) "
                        f"[{selected_room['name']}]"
                    )

                    faculty_busy.add(
                        (faculty_id, day, period)
                    )

                    room_busy.add(
                        (selected_room['id'], day, period)
                    )

                    filled = True

                    break

                # still empty
                if not filled:

                    tt[day][period] = "Library"

    return timetable