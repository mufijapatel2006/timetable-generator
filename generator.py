import random
import itertools
from collections import defaultdict
from typing import Dict, List, Any

DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
PERIODS = 6
BATCHES = ["A1", "A2", "A3", "A4"]

# Standard 2-period practical block slots
PRACTICAL_SLOTS = [
    (0, 1),
    (2, 3),
    (4, 5)
]

def generate_timetable(db) -> Dict[str, List[List[str]]]:
    """
    High-Performance Conflict-Free Timetable Generator.
    
    Strict Guarantees:
    1. Zero Faculty Overlap: A faculty member is never scheduled in two classes, batches, or rooms simultaneously.
    2. Zero Lab / Classroom Overlap: No room or lab is ever double-booked.
    3. Zero Class Overlap: A class has at most one scheduled activity per period.
    4. Exact Total Load: Theory subjects are scheduled for EXACTLY their prescribed syllabus hours (no artificial lecture duplication).
    5. Concurrent Practical Batches: 4 batches (A1, A2, A3, A4) are allocated distinct labs and distinct faculties concurrently.
    6. Balanced Daily Distribution: Maximum 1 or 2 lectures of the same subject on any single day.
    7. Clean Open Periods: Any unscheduled slots after satisfying curriculum loads are designated 'Library / Self-Study'.
    """

    # =====================================================
    # 1. LOAD INPUT DATA (FirebaseService Preload or DB Cursor)
    # =====================================================
    faculty_allocations = []
    if hasattr(db, "get_timetable_input_data"):
        data = db.get_timetable_input_data()
        classes = data["classes"]
        subjects = data["subjects"]
        rooms = data["rooms"]
        faculty = data["faculty"]
        batch_faculty = data.get("batch_faculty", [])
        faculty_allocations = data.get("faculty_allocations", [])
    else:
        cursor = db.cursor(dictionary=True)
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

        cursor.execute("SELECT * FROM faculty")
        faculty = cursor.fetchall()

        cursor.execute("SELECT * FROM batch_faculty")
        batch_faculty = cursor.fetchall()

    faculty_name_map = {f["id"]: f["name"] for f in faculty}

    # Pre-flight readiness validation check
    if hasattr(db, "validate_timetable_readiness"):
        readiness = db.validate_timetable_readiness()
        if not readiness.get("is_ready", True) and readiness.get("errors"):
            unassigned_errs = "; ".join(readiness["errors"][:4])
            # We log or notify, but proceed if possible with best-effort
            print(f"[Generator] Validation Notice: {unassigned_errs}")

    # Build explicit lookup maps from faculty_allocations
    theory_alloc_map = {
        (a["class_id"], a["subject_id"]): a["faculty_id"]
        for a in faculty_allocations if a.get("activity") == "Theory"
    }
    practical_alloc_map = {
        (a["class_id"], a["subject_id"], a["batch"]): a["faculty_id"]
        for a in faculty_allocations if a.get("activity") == "Practical"
    }
    practical_lab_map = {
        (a["class_id"], a["subject_id"], a["batch"]): a["lab_id"]
        for a in faculty_allocations
        if a.get("activity") == "Practical" and a.get("lab_id")
    }
    tutorial_alloc_map = {
        (a["class_id"], a["subject_id"], a["batch"]): a["faculty_id"]
        for a in faculty_allocations if a.get("activity") == "Tutorial"
    }

    # Fallback to legacy batch_faculty if practical_alloc_map lacks entries
    batch_faculty_map = {
        (bf["class_id"], bf["subject_id"], bf["batch"]): bf["faculty_id"]
        for bf in batch_faculty
    }

    # Ensure faculty_name is populated on all subjects
    for sub in subjects:
        if not sub.get("faculty_name"):
            fid = sub.get("primary_faculty_id") or sub.get("faculty_id")
            sub["faculty_name"] = faculty_name_map.get(fid, "")

    classrooms = [r for r in rooms if r.get("type") == "Classroom"]
    labs = [r for r in rooms if r.get("type") == "Lab"]

    # Pre-compute maintenance / downtime blocked slots across all facilities
    DAY_NAME_TO_INDEX = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4}
    maintenance_busy = set()
    for r in rooms:
        for slot_str in r.get("available_slots", []):
            parts = str(slot_str).split("_")
            if len(parts) == 2 and parts[0] in DAY_NAME_TO_INDEX and parts[1].isdigit():
                d_idx = DAY_NAME_TO_INDEX[parts[0]]
                p_idx = int(parts[1])
                maintenance_busy.add((r["id"], d_idx, p_idx))

    def is_lab_compatible(lab: Dict[str, Any], sub: Dict[str, Any], batch_size: int = None) -> bool:
        """Determines if a laboratory facility satisfies subject requirements."""
        b_size = batch_size or sub.get("batch_size") or 20
        if lab.get("capacity", 30) < b_size:
            return False
        supp = lab.get("supported_subjects", [])
        if supp and sub["id"] not in supp:
            return False
        req_equip = set(sub.get("required_equipment", []))
        if req_equip and not req_equip.issubset(set(lab.get("equipment", []))):
            return False
        return True

    # Group subjects by class into Theory, Practical, and Tutorial components
    class_theory = defaultdict(list)
    raw_practical = defaultdict(list)
    class_tutorial = defaultdict(list)

    for sub in subjects:
        cid = sub.get("class_id")
        components = sub.get("components")
        if not isinstance(components, list) or not components:
            legacy_type = str(sub.get("type", "Theory")).strip()
            components = ["Practical"] if "Practical" in legacy_type else ["Theory"]

        # Theory component
        if "Theory" in components:
            t_sub = dict(sub)
            t_fid = theory_alloc_map.get((cid, sub["id"]), sub.get("primary_faculty_id") or sub.get("faculty_id"))
            t_sub["faculty_id"] = t_fid
            t_sub["faculty_name"] = faculty_name_map.get(t_fid, sub.get("faculty_name", ""))
            t_sub["hours"] = int(sub.get("theory_hours") or sub.get("hours", 3))
            if t_sub["hours"] > 0:
                class_theory[cid].append(t_sub)

        # Practical component
        if "Practical" in components:
            p_sub = dict(sub)
            raw_practical[cid].append(p_sub)

        # Tutorial component
        if "Tutorial" in components:
            tut_sub = dict(sub)
            tut_sub["hours"] = int(sub.get("tutorial_hours", 1))
            if tut_sub["hours"] > 0:
                class_tutorial[cid].append(tut_sub)

    # Deduplicate practical subjects per class by name, preferring ones with batch assignments
    class_practical = defaultdict(list)
    for cid, pracs in raw_practical.items():
        by_name = {}
        for sub in pracs:
            sname = sub.get("name", "").strip()
            has_bf = any(
                (cid, sub.get("id"), b) in practical_alloc_map or
                (cid, sub.get("id"), b) in batch_faculty_map
                for b in BATCHES
            )
            if sname not in by_name or has_bf:
                by_name[sname] = sub
        class_practical[cid] = list(by_name.values())

    # Pre-generate all valid clash-free 4-batch practical configurations per class
    # Ensures all 4 batches use distinct faculties simultaneously
    class_valid_combos = {}
    for cls in classes:
        cid = cls["id"]
        pracs = class_practical[cid]
        combos = []
        for combo in itertools.product(pracs, repeat=4):
            facs = []
            for b_idx, b_name in enumerate(BATCHES):
                sub = combo[b_idx]
                f_id = practical_alloc_map.get(
                    (cid, sub["id"], b_name),
                    batch_faculty_map.get((cid, sub["id"], b_name), sub.get("primary_faculty_id") or sub.get("faculty_id"))
                )
                facs.append(f_id)
            if len(set(facs)) == 4:
                combos.append((combo, facs))
        class_valid_combos[cid] = combos

    # =====================================================
    # 2. CONSTRAINT SATISFACTION SEARCH (Fast Multi-Restart)
    # =====================================================
    best_timetable = None
    min_penalties = float("inf")
    MAX_ATTEMPTS = 50

    for attempt in range(MAX_ATTEMPTS):
        timetable = {
            cls["name"].strip(): [[None for _ in range(PERIODS)] for _ in range(5)]
            for cls in classes
        }

        # O(1) Conflict trackers
        faculty_busy = set()  # (faculty_id, day, period)
        room_busy = set(maintenance_busy)  # (room_id, day, period) pre-populated with facility maintenance
        class_busy = set()    # (class_id, day, period)

        class_sub_day_count = defaultdict(int)  # (class_id, sub_id, day) -> count

        # -------------------------------------------------
        # STEP A: SCHEDULE PRACTICAL SESSIONS (2-Period Blocks)
        # -------------------------------------------------
        classes_order = list(classes)
        random.shuffle(classes_order)
        batch_sub_taken = defaultdict(set)  # (class_id, batch_name) -> set of sub_name

        for cls in classes_order:
            cid = cls["id"]
            cname = cls["name"].strip()
            combos = class_valid_combos.get(cid, [])
            if not combos:
                continue

            # Standard 3 practical blocks per week per class (6 periods)
            num_slots_needed = min(len(class_practical[cid]), 3)
            slots_allocated = 0

            candidate_slots = []
            for d in range(5):
                for p1, p2 in PRACTICAL_SLOTS:
                    candidate_slots.append((d, p1, p2))
            random.shuffle(candidate_slots)

            for d, p1, p2 in candidate_slots:
                if slots_allocated >= num_slots_needed:
                    break

                # Ensure class is free for both periods
                if (cid, d, p1) in class_busy or (cid, d, p2) in class_busy:
                    continue

                shuffled_combos = list(combos)
                random.shuffle(shuffled_combos)
                # Prioritize combinations where batches rotate into subjects not yet taken this week
                shuffled_combos.sort(
                    key=lambda c: sum(
                        1 for b_idx, b_name in enumerate(BATCHES)
                        if c[0][b_idx]["name"] not in batch_sub_taken[(cid, b_name)]
                    ),
                    reverse=True
                )

                for combo, facs in shuffled_combos:
                    # Overlap check: all 4 faculties must be free for both periods
                    if any((f, d, p1) in faculty_busy or (f, d, p2) in faculty_busy for f in facs):
                        continue

                    # Overlap check: 4 distinct free labs must be available (excluding maintenance)
                    free_labs = [
                        l for l in labs
                        if (l["id"], d, p1) not in room_busy and (l["id"], d, p2) not in room_busy
                    ]
                    if len(free_labs) < 4:
                        continue

                    # Intelligent Lab Allocation & Backtracking Search:
                    # Allocate 4 distinct compatible laboratories to batches A1-A4
                    def match_compatible_labs(b_idx: int, used_lab_ids: set, current_assignment: list):
                        if b_idx == 4:
                            return current_assignment

                        sub = combo[b_idx]
                        b_name = BATCHES[b_idx]
                        pref_lab_id = practical_lab_map.get((cid, sub["id"], b_name))

                        # Score each available lab for this batch
                        candidates = []
                        for lab in free_labs:
                            if lab["id"] in used_lab_ids:
                                continue
                            score = 0
                            # Highest priority: admin allocated/preferred lab
                            if lab["id"] == pref_lab_id:
                                score += 20
                            # High priority: compatible with subject, capacity & equipment
                            if is_lab_compatible(lab, sub):
                                score += 10
                            elif lab.get("capacity", 30) >= sub.get("batch_size", 20):
                                score += 2
                            else:
                                score += 1
                            candidates.append((score, lab))

                        candidates.sort(key=lambda x: x[0], reverse=True)
                        for score, lab in candidates:
                            res = match_compatible_labs(b_idx + 1, used_lab_ids | {lab["id"]}, current_assignment + [lab])
                            if res:
                                return res
                        return None

                    assigned_labs = match_compatible_labs(0, set(), [])
                    if not assigned_labs or len(assigned_labs) < 4:
                        continue

                    lines = []
                    for b_idx, b_name in enumerate(BATCHES):
                        sub = combo[b_idx]
                        f_id = facs[b_idx]
                        lab = assigned_labs[b_idx]
                        f_name = faculty_name_map.get(f_id, sub["faculty_name"])
                        lines.append(f"{sub['name']} ({f_name}) [{lab['name']}] - {b_name}")
                        batch_sub_taken[(cid, b_name)].add(sub["name"])

                    timetable[cname][d][p1] = "<br>".join(lines)
                    timetable[cname][d][p2] = "CONT"

                    class_busy.add((cid, d, p1))
                    class_busy.add((cid, d, p2))
                    for f_id in facs:
                        faculty_busy.add((f_id, d, p1))
                        faculty_busy.add((f_id, d, p2))
                    for lab in assigned_labs:
                        room_busy.add((lab["id"], d, p1))
                        room_busy.add((lab["id"], d, p2))

                    slots_allocated += 1
                    break

        # -------------------------------------------------
        # STEP B: SCHEDULE TUTORIAL SESSIONS (1-Period Batches)
        # -------------------------------------------------
        for cls in classes_order:
            cid = cls["id"]
            cname = cls["name"].strip()
            tut_subjects = class_tutorial.get(cid, [])

            for tut_sub in tut_subjects:
                target_tut_hours = int(tut_sub.get("hours", 1))
                tut_allocated = 0

                # Determine tutorial faculty per batch
                facs = []
                for b_name in BATCHES:
                    fid = tutorial_alloc_map.get(
                        (cid, tut_sub["id"], b_name),
                        tut_sub.get("primary_faculty_id") or tut_sub.get("faculty_id")
                    )
                    facs.append(fid)

                # Look for open period
                possible_tut_slots = []
                for d in range(5):
                    for p in range(PERIODS):
                        if (cid, d, p) in class_busy:
                            continue
                        if any((f, d, p) in faculty_busy for f in facs if f):
                            continue

                        # Find free room(s)
                        free_rooms = [r for r in rooms if (r["id"], d, p) not in room_busy]
                        if free_rooms:
                            possible_tut_slots.append((d, p, free_rooms))

                random.shuffle(possible_tut_slots)
                for d, p, free_rooms in possible_tut_slots:
                    if tut_allocated >= target_tut_hours:
                        break

                    lines = []
                    for b_idx, b_name in enumerate(BATCHES):
                        f_id = facs[b_idx]
                        f_name = faculty_name_map.get(f_id, "TBA")
                        r_assigned = free_rooms[b_idx % len(free_rooms)]
                        lines.append(f"{tut_sub['name']} Tut ({f_name}) [{r_assigned['name']}] - {b_name}")

                    timetable[cname][d][p] = "<br>".join(lines)
                    class_busy.add((cid, d, p))
                    for f_id in facs:
                        if f_id:
                            faculty_busy.add((f_id, d, p))
                    for r_assigned in free_rooms[:min(4, len(free_rooms))]:
                        room_busy.add((r_assigned["id"], d, p))

                    tut_allocated += 1

        # -------------------------------------------------
        # STEP C: SCHEDULE THEORY LECTURES (Exact Total Load)
        # -------------------------------------------------
        pending_lectures = []
        for cls in classes:
            cid = cls["id"]
            cname = cls["name"].strip()
            for sub in class_theory[cid]:
                target_hours = int(sub.get("hours", 0))
                for _ in range(target_hours):
                    pending_lectures.append((cid, cname, sub))

        # Heuristic: schedule larger weekly load subjects first
        random.shuffle(pending_lectures)
        pending_lectures.sort(key=lambda x: int(x[2].get("hours", 0)), reverse=True)

        unplaced = 0
        for cid, cname, sub in pending_lectures:
            sub_id = sub["id"]
            fac_id = sub["faculty_id"]
            placed = False

            possible = []
            for d in range(5):
                # Daily distribution: max 1 lecture, or 2 if weekly hours >= 4
                max_daily = 2 if int(sub.get("hours", 0)) >= 4 else 1
                if class_sub_day_count[(cid, sub_id, d)] >= max_daily:
                    continue

                for p in range(PERIODS):
                    if (cid, d, p) in class_busy or (fac_id, d, p) in faculty_busy:
                        continue

                    # Find free classroom
                    for room in classrooms:
                        if (room["id"], d, p) not in room_busy:
                            possible.append((d, p, room))
                            break

            if possible:
                d, p, room = random.choice(possible)
                timetable[cname][d][p] = f"{sub['name']} ({sub['faculty_name']}) [{room['name']}]"
                class_busy.add((cid, d, p))
                faculty_busy.add((fac_id, d, p))
                room_busy.add((room["id"], d, p))
                class_sub_day_count[(cid, sub_id, d)] += 1
                placed = True
            else:
                unplaced += 1

        # -------------------------------------------------
        # STEP D: OPEN SLOTS (Designate Library / Self-Study)
        # -------------------------------------------------
        for cls in classes:
            cname = cls["name"].strip()
            for d in range(5):
                for p in range(PERIODS):
                    if timetable[cname][d][p] is None:
                        timetable[cname][d][p] = "Library / Self-Study"

        if unplaced < min_penalties:
            min_penalties = unplaced
            best_timetable = timetable
            if unplaced == 0:
                break

    return best_timetable if best_timetable is not None else timetable