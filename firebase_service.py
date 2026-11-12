import os
import json
import math
import logging
from typing import List, Dict, Any, Optional
from datetime import datetime
from cachetools import TTLCache
from werkzeug.security import generate_password_hash, check_password_hash

# Configure logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("FirebaseService")

CREDENTIAL_FILES = [
    "serviceAccountKey.json",
    "firebase_credentials.json",
    "firebase-adminsdk.json",
]

BACKUP_DATA_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "database",
    "backup_data.json"
)

DRAFT_TIMETABLE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "database",
    "draft_timetable.json"
)

PUBLISHED_TIMETABLE_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "database",
    "published_timetable.json"
)

TIMETABLE_HISTORY_FILE = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "database",
    "timetable_history.json"
)

class Record(dict):
    """
    Dual-access record supporting:
    - Dictionary key access (rec['name'])
    - Tuple index access (rec[1]) for template compatibility
    - Attribute access for convenience
    """
    def __init__(self, data_dict: Dict[str, Any], tuple_keys: List[str]):
        super().__init__(data_dict)
        self._tuple_keys = tuple_keys
        self._tuple = tuple(data_dict.get(k) for k in tuple_keys)

    def __getitem__(self, key):
        if isinstance(key, int):
            return self._tuple[key]
        return super().__getitem__(key)

    def __getattr__(self, name):
        if name in self:
            return self[name]
        raise AttributeError(f"'Record' object has no attribute '{name}'")


class FirebaseService:
    _instance = None

    def __new__(cls, *args, **kwargs):
        if cls._instance is None:
            cls._instance = super(FirebaseService, cls).__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        if self._initialized:
            return

        self.db = None
        self.is_connected = False
        self.cache = TTLCache(maxsize=200, ttl=300)
        self._cached_master_timetable = None
        self._cached_draft_timetable = None
        self._cached_published_timetable = None
        self._local_data: Dict[str, List[Dict[str, Any]]] = {}
        self._load_local_data()

        self._init_firebase()
        self._init_users()
        self._init_timetable_storage()
        self._initialized = True

    def _init_firebase(self):
        """Attempts to initialize Firebase Admin SDK from certificate or env."""
        cred_path = None
        for path in [
            os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"),
            os.environ.get("FIREBASE_CREDENTIALS"),
            *[os.path.join(os.path.dirname(os.path.abspath(__file__)), f) for f in CREDENTIAL_FILES]
        ]:
            if path and os.path.isfile(path):
                cred_path = path
                break

        if cred_path:
            try:
                import firebase_admin
                from firebase_admin import credentials, firestore

                if not firebase_admin._apps:
                    cred = credentials.Certificate(cred_path)
                    firebase_admin.initialize_app(cred)
                self.db = firestore.client()
                self.is_connected = True
                logger.info(f"Connected to Firebase Firestore using credentials from: {cred_path}")
            except Exception as e:
                logger.warning(f"Failed to initialize Firebase Admin with {cred_path}: {e}")
                self.is_connected = False
        else:
            logger.info("No serviceAccountKey.json found. Operating in local mode with backup data.")
            self.is_connected = False

        if not self.is_connected:
            self._load_local_data()

    def _load_local_data(self):
        """Loads data from backup_data.json as safe local storage."""
        if os.path.exists(BACKUP_DATA_FILE):
            with open(BACKUP_DATA_FILE, "r", encoding="utf-8") as f:
                self._local_data = json.load(f)
        else:
            self._local_data = {
                "classes": [],
                "faculty": [],
                "rooms": [],
                "subjects": [],
                "batch_faculty": [],
                "batch_subject": [],
                "faculty_allocations": []
            }
        self._local_data.setdefault("faculty_allocations", [])

    def _save_local_data(self):
        """Persists local fallback data to disk."""
        if not self.is_connected:
            os.makedirs(os.path.dirname(BACKUP_DATA_FILE), exist_ok=True)
            with open(BACKUP_DATA_FILE, "w", encoding="utf-8") as f:
                json.dump(self._local_data, f, indent=2, default=str)

    def invalidate_cache(self):
        """Clears memory cache on any data mutation."""
        self.cache.clear()
        self._cached_master_timetable = None

    # =========================================================================
    # CLASSES
    # =========================================================================
    def get_classes(self) -> List[Record]:
        cache_key = "classes"
        if cache_key in self.cache:
            return self.cache[cache_key]

        tuple_keys = ["id", "name"]
        records = []
        if self.is_connected:
            try:
                docs = self.db.collection("classes").stream()
                for doc in docs:
                    d = doc.to_dict()
                    d["id"] = int(d.get("id", doc.id))
                    records.append(Record(d, tuple_keys))
            except Exception as e:
                logger.warning(f"Firestore get_classes error: {e}. Using local data.")
                for item in self._local_data.get("classes", []):
                    records.append(Record(dict(item), tuple_keys))
        else:
            for item in self._local_data.get("classes", []):
                records.append(Record(dict(item), tuple_keys))

        records.sort(key=lambda r: r["id"])
        self.cache[cache_key] = records
        return records

    def add_class(self, name: str) -> int:
        classes = self.get_classes()
        new_id = max([c["id"] for c in classes], default=0) + 1
        data = {"id": new_id, "name": name.strip()}

        if self.is_connected:
            self.db.collection("classes").document(str(new_id)).set(data)
        else:
            self._local_data.setdefault("classes", []).append(data)
            self._save_local_data()

        self.invalidate_cache()
        return new_id

    # =========================================================================
    # FACULTY
    # =========================================================================
    def get_faculty(self) -> List[Record]:
        cache_key = "faculty"
        if cache_key in self.cache:
            return self.cache[cache_key]

        tuple_keys = ["id", "name"]
        records = []
        if self.is_connected:
            try:
                docs = self.db.collection("faculty").stream()
                for doc in docs:
                    d = doc.to_dict()
                    d["id"] = int(d.get("id", doc.id))
                    records.append(Record(d, tuple_keys))
            except Exception as e:
                logger.warning(f"Firestore get_faculty error: {e}. Using local data.")
                for item in self._local_data.get("faculty", []):
                    records.append(Record(dict(item), tuple_keys))
        else:
            for item in self._local_data.get("faculty", []):
                records.append(Record(dict(item), tuple_keys))

        records.sort(key=lambda r: r["id"])
        self.cache[cache_key] = records
        return records

    def add_faculty(self, name: str) -> int:
        fac = self.get_faculty()
        new_id = max([f["id"] for f in fac], default=0) + 1
        data = {"id": new_id, "name": name.strip()}

        if self.is_connected:
            self.db.collection("faculty").document(str(new_id)).set(data)
        else:
            self._local_data.setdefault("faculty", []).append(data)
            self._save_local_data()

        self.invalidate_cache()
        return new_id

    # =========================================================================
    # ROOMS & LABORATORIES
    # =========================================================================
    def _normalize_room(self, d: Dict[str, Any]) -> Dict[str, Any]:
        """
        Normalizes Room / Laboratory entity with safe defaults for:
        id, name, type, code, department, capacity, equipment, supported_subjects, available_slots
        """
        room_id = int(d.get("id", 0))
        room_type = str(d.get("type", "Classroom")).strip()
        if "Lab" in room_type or "lab" in room_type.lower():
            room_type = "Lab"
        else:
            room_type = "Classroom"

        name = str(d.get("name", f"Facility {room_id}")).strip()
        prefix = "LAB" if room_type == "Lab" else "CLS"
        code = str(d.get("code") or f"{prefix}-{room_id:02d}").strip()
        department = str(d.get("department") or "Computer Science & Engineering").strip()

        try:
            capacity = int(d.get("capacity") or (30 if room_type == "Lab" else 60))
        except (ValueError, TypeError):
            capacity = 30 if room_type == "Lab" else 60

        # Equipment list
        equip_raw = d.get("equipment")
        if isinstance(equip_raw, list):
            equipment = [str(e).strip() for e in equip_raw if str(e).strip()]
        elif isinstance(equip_raw, str):
            equipment = [e.strip() for e in equip_raw.split(",") if e.strip()]
        else:
            equipment = ["High-Performance Workstations", "High-Speed LAN"] if room_type == "Lab" else ["AV Projector", "Smart Board"]

        # Supported subjects (List of subject IDs compatible with this lab)
        supp_raw = d.get("supported_subjects")
        if isinstance(supp_raw, list):
            supported_subjects = [int(s) for s in supp_raw if str(s).isdigit()]
        elif isinstance(supp_raw, str):
            supported_subjects = [int(s.strip()) for s in supp_raw.split(",") if s.strip().isdigit()]
        else:
            supported_subjects = []

        # Available / maintenance slots: list of blocked slot strings, e.g. ["Mon_0", "Wed_2"]
        avail_raw = d.get("available_slots") or d.get("maintenance_slots") or []
        if isinstance(avail_raw, list):
            available_slots = [str(s).strip() for s in avail_raw if str(s).strip()]
        elif isinstance(avail_raw, str):
            available_slots = [s.strip() for s in avail_raw.split(",") if s.strip()]
        else:
            available_slots = []

        return {
            "id": room_id,
            "name": name,
            "type": room_type,
            "code": code,
            "department": department,
            "capacity": capacity,
            "equipment": equipment,
            "supported_subjects": supported_subjects,
            "available_slots": available_slots
        }

    def get_rooms(self) -> List[Record]:
        cache_key = "rooms"
        if cache_key in self.cache:
            return self.cache[cache_key]

        tuple_keys = ["id", "name", "type", "code", "department", "capacity", "equipment", "supported_subjects", "available_slots"]
        records = []
        if self.is_connected:
            try:
                docs = self.db.collection("rooms").stream()
                for doc in docs:
                    d = doc.to_dict()
                    d["id"] = int(d.get("id", doc.id))
                    norm = self._normalize_room(d)
                    records.append(Record(norm, tuple_keys))
            except Exception as e:
                logger.warning(f"Firestore get_rooms error: {e}. Using local data.")
                for item in self._local_data.get("rooms", []):
                    norm = self._normalize_room(dict(item))
                    records.append(Record(norm, tuple_keys))
        else:
            for item in self._local_data.get("rooms", []):
                norm = self._normalize_room(dict(item))
                records.append(Record(norm, tuple_keys))

        records.sort(key=lambda r: r["id"])
        self.cache[cache_key] = records
        return records

    def get_labs(self) -> List[Record]:
        """Returns all rooms registered as Laboratory facilities."""
        return [r for r in self.get_rooms() if r.get("type") == "Lab"]

    def get_room(self, room_id: int) -> Optional[Record]:
        rooms = self.get_rooms()
        for r in rooms:
            if r["id"] == int(room_id):
                return r
        return None

    def get_compatible_labs_for_subject(self, subject_id: int, batch_size: Optional[int] = None) -> List[Record]:
        """
        Identifies laboratories that satisfy:
        1. Lab capacity >= batch_size.
        2. Subject mapping: subject_id in lab.supported_subjects (or lab has open mapping).
        3. Equipment requirements: lab has all required equipment specified by the subject.
        """
        subject = self.get_subject(int(subject_id))
        labs = self.get_labs()
        if not labs:
            return []

        req_equipment = set(subject.get("required_equipment", [])) if subject else set()
        b_size = batch_size or (subject.get("batch_size") if subject else None) or 20

        compatible = []
        for lab in labs:
            # Capacity check
            if lab.get("capacity", 30) < b_size:
                continue

            # Supported subjects check
            supported = lab.get("supported_subjects", [])
            if supported and int(subject_id) not in supported:
                continue

            # Equipment requirement check
            lab_equip = set(lab.get("equipment", []))
            if req_equipment and not req_equipment.issubset(lab_equip):
                continue

            compatible.append(lab)

        # Fallback to labs with sufficient capacity if specific mappings are unconfigured
        if not compatible:
            compatible = [l for l in labs if l.get("capacity", 30) >= b_size]
        if not compatible:
            compatible = list(labs)

        return compatible

    def add_room(
        self,
        name: str,
        room_type: str,
        code: str = None,
        department: str = "Computer Science & Engineering",
        capacity: int = 30,
        equipment: List[str] = None,
        supported_subjects: List[int] = None,
        available_slots: List[str] = None
    ) -> int:
        rooms = self.get_rooms()
        new_id = max([r["id"] for r in rooms], default=0) + 1
        prefix = "LAB" if room_type == "Lab" else "CLS"
        clean_code = str(code).strip() if code else f"{prefix}-{new_id:02d}"

        if equipment is None:
            equipment = ["High-Performance Workstations", "High-Speed LAN"] if room_type == "Lab" else ["AV Projector", "Smart Board"]
        if supported_subjects is None:
            supported_subjects = []
        if available_slots is None:
            available_slots = []

        data = {
            "id": new_id,
            "name": name.strip(),
            "type": room_type.strip(),
            "code": clean_code,
            "department": department.strip(),
            "capacity": int(capacity),
            "equipment": [str(e).strip() for e in equipment if str(e).strip()],
            "supported_subjects": [int(s) for s in supported_subjects if str(s).isdigit()],
            "available_slots": [str(s).strip() for s in available_slots if str(s).strip()]
        }

        if self.is_connected:
            self.db.collection("rooms").document(str(new_id)).set(data)
        else:
            self._local_data.setdefault("rooms", []).append(data)
            self._save_local_data()

        self.invalidate_cache()
        return new_id

    def edit_room(
        self,
        room_id: int,
        name: str,
        room_type: str,
        code: str = None,
        department: str = None,
        capacity: int = None,
        equipment: List[str] = None,
        supported_subjects: List[int] = None,
        available_slots: List[str] = None
    ):
        room_id = int(room_id)
        existing = self.get_room(room_id)
        if not existing:
            return

        prefix = "LAB" if room_type == "Lab" else "CLS"
        clean_code = str(code).strip() if code else (existing.get("code") or f"{prefix}-{room_id:02d}")
        clean_dept = str(department).strip() if department is not None else existing.get("department", "Computer Science & Engineering")
        clean_cap = int(capacity) if capacity is not None else existing.get("capacity", 30)

        clean_equip = [str(e).strip() for e in equipment if str(e).strip()] if equipment is not None else existing.get("equipment", [])
        clean_subs = [int(s) for s in supported_subjects if str(s).isdigit()] if supported_subjects is not None else existing.get("supported_subjects", [])
        clean_slots = [str(s).strip() for s in available_slots if str(s).strip()] if available_slots is not None else existing.get("available_slots", [])

        update_data = {
            "name": name.strip(),
            "type": room_type.strip(),
            "code": clean_code,
            "department": clean_dept,
            "capacity": clean_cap,
            "equipment": clean_equip,
            "supported_subjects": clean_subs,
            "available_slots": clean_slots
        }

        if self.is_connected:
            self.db.collection("rooms").document(str(room_id)).update(update_data)
        else:
            for item in self._local_data.get("rooms", []):
                if item["id"] == room_id:
                    item.update(update_data)
                    break
            self._save_local_data()

        self.invalidate_cache()

    def update_lab_availability(self, room_id: int, blocked_slots: List[str]):
        """Sets maintenance/downtime periods where this laboratory cannot be scheduled."""
        room_id = int(room_id)
        clean_slots = [str(s).strip() for s in blocked_slots if str(s).strip()]
        if self.is_connected:
            self.db.collection("rooms").document(str(room_id)).update({"available_slots": clean_slots})
        else:
            for item in self._local_data.get("rooms", []):
                if item["id"] == room_id:
                    item["available_slots"] = clean_slots
                    break
            self._save_local_data()

        self.invalidate_cache()

    def delete_room(self, room_id: int):
        room_id = int(room_id)
        if self.is_connected:
            self.db.collection("rooms").document(str(room_id)).delete()
        else:
            self._local_data["rooms"] = [
                r for r in self._local_data.get("rooms", [])
                if r["id"] != room_id
            ]
            self._save_local_data()

        self.invalidate_cache()

    # =========================================================================
    # SUBJECTS (Multi-Component: Theory, Practical, Tutorial)
    # =========================================================================
    def _normalize_subject(self, d: Dict[str, Any], faculty_map: Dict[int, str]) -> Dict[str, Any]:
        sub_id = int(d.get("id", 0))
        class_id = int(d.get("class_id", 0)) if d.get("class_id") is not None else None

        primary_id = d.get("primary_faculty_id") or d.get("faculty_id")
        primary_faculty_id = int(primary_id) if primary_id is not None else None
        faculty_name = faculty_map.get(primary_faculty_id, d.get("faculty_name", ""))

        # Components: ["Theory", "Practical", "Tutorial"]
        components = d.get("components")
        if not isinstance(components, list) or not components:
            legacy_type = str(d.get("type", "Theory")).strip()
            if "Practical" in legacy_type:
                components = ["Practical"]
            elif "Tutorial" in legacy_type:
                components = ["Tutorial"]
            else:
                components = ["Theory"]

        legacy_hours = int(d.get("hours", 0))
        theory_hours = int(d.get("theory_hours", legacy_hours if "Theory" in components else 0))
        practical_hours = int(d.get("practical_hours", (legacy_hours if "Practical" in components and "Theory" not in components else 2) if "Practical" in components else 0))
        tutorial_hours = int(d.get("tutorial_hours", 1 if "Tutorial" in components else 0))

        total_hours = (theory_hours if "Theory" in components else 0) + \
                      (practical_hours if "Practical" in components else 0) + \
                      (tutorial_hours if "Tutorial" in components else 0)
        if total_hours == 0 and legacy_hours > 0:
            total_hours = legacy_hours

        type_display = ", ".join(components) if components else d.get("type", "Theory")

        # Eligible faculty pools
        prac_pool = [int(x) for x in d.get("practical_faculty_pool", []) if str(x).isdigit()]
        tut_pool = [int(x) for x in d.get("tutorial_faculty_pool", []) if str(x).isdigit()]

        # Laboratory requirements
        req_equip_raw = d.get("required_equipment")
        if isinstance(req_equip_raw, list):
            req_equip = [str(e).strip() for e in req_equip_raw if str(e).strip()]
        elif isinstance(req_equip_raw, str):
            req_equip = [e.strip() for e in req_equip_raw.split(",") if e.strip()]
        else:
            req_equip = []

        try:
            batch_size = int(d.get("batch_size") or 20)
        except (ValueError, TypeError):
            batch_size = 20

        pref_labs_raw = d.get("preferred_labs")
        if isinstance(pref_labs_raw, list):
            pref_labs = [int(x) for x in pref_labs_raw if str(x).isdigit()]
        elif isinstance(pref_labs_raw, str):
            pref_labs = [int(x.strip()) for x in pref_labs_raw.split(",") if x.strip().isdigit()]
        else:
            pref_labs = []

        return {
            "id": sub_id,
            "name": str(d.get("name", "")).strip(),
            "type": type_display,
            "hours": total_hours,
            "class_id": class_id,
            "faculty_id": primary_faculty_id,
            "faculty_name": faculty_name,
            "primary_faculty_id": primary_faculty_id,
            "components": components,
            "academic_year": str(d.get("academic_year") or "2024-2025").strip(),
            "semester": str(d.get("semester") or "Semester 1").strip(),
            "theory_hours": theory_hours,
            "practical_hours": practical_hours,
            "tutorial_hours": tutorial_hours,
            "practical_faculty_pool": prac_pool,
            "tutorial_faculty_pool": tut_pool,
            "match_tutorial_batches": bool(d.get("match_tutorial_batches", True)),
            "required_equipment": req_equip,
            "batch_size": batch_size,
            "preferred_labs": pref_labs
        }

    def get_subjects(self, fetch_faculty_names: bool = True) -> List[Record]:
        cache_key = f"subjects_{fetch_faculty_names}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        faculty_map = {}
        if fetch_faculty_names:
            faculty_list = self.get_faculty()
            faculty_map = {f["id"]: f["name"] for f in faculty_list}

        tuple_keys = [
            "id", "name", "type", "hours", "class_id", "faculty_id", "faculty_name",
            "components", "academic_year", "semester", "primary_faculty_id",
            "theory_hours", "practical_hours", "tutorial_hours",
            "practical_faculty_pool", "tutorial_faculty_pool", "match_tutorial_batches",
            "required_equipment", "batch_size", "preferred_labs"
        ]
        records = []

        if self.is_connected:
            try:
                docs = self.db.collection("subjects").stream()
                for doc in docs:
                    d = doc.to_dict()
                    d["id"] = int(d.get("id", doc.id))
                    norm = self._normalize_subject(d, faculty_map)
                    records.append(Record(norm, tuple_keys))
            except Exception as e:
                logger.warning(f"Firestore get_subjects error: {e}. Using local data.")
                for item in self._local_data.get("subjects", []):
                    norm = self._normalize_subject(dict(item), faculty_map)
                    records.append(Record(norm, tuple_keys))
        else:
            for item in self._local_data.get("subjects", []):
                norm = self._normalize_subject(dict(item), faculty_map)
                records.append(Record(norm, tuple_keys))

        records.sort(key=lambda r: r["id"])
        self.cache[cache_key] = records
        return records

    def get_subject(self, subject_id: int) -> Optional[Record]:
        subjects = self.get_subjects()
        for s in subjects:
            if s["id"] == subject_id:
                return s
        return None

    def add_subject(
        self,
        name: str,
        class_id: int = None,
        primary_faculty_id: int = None,
        components: List[str] = None,
        theory_hours: int = 3,
        practical_hours: int = 2,
        tutorial_hours: int = 1,
        practical_faculty_pool: List[int] = None,
        tutorial_faculty_pool: List[int] = None,
        academic_year: str = "2024-2025",
        semester: str = "Semester 1",
        match_tutorial_batches: bool = True,
        required_equipment: List[str] = None,
        batch_size: int = 20,
        preferred_labs: List[int] = None,
        # Legacy positional/keyword parameter support
        sub_type: str = None,
        hours: int = None,
        faculty_id: int = None
    ) -> int:
        subjects = self.get_subjects(fetch_faculty_names=False)
        new_id = max([s["id"] for s in subjects], default=0) + 1

        # Handle legacy call signature: add_subject(name, sub_type, hours, class_id, faculty_id)
        if primary_faculty_id is None and faculty_id is not None:
            primary_faculty_id = int(faculty_id)
        if class_id is not None:
            class_id = int(class_id)
        if components is None:
            if sub_type:
                components = ["Practical"] if "Practical" in sub_type else ["Theory"]
            else:
                components = ["Theory"]

        if hours is not None:
            if "Practical" in components and "Theory" not in components:
                practical_hours = int(hours)
            else:
                theory_hours = int(hours)

        faculty_map = {f["id"]: f["name"] for f in self.get_faculty()}
        faculty_name = faculty_map.get(primary_faculty_id, "")

        if practical_faculty_pool is None:
            practical_faculty_pool = []
        if tutorial_faculty_pool is None:
            tutorial_faculty_pool = []
        if required_equipment is None:
            required_equipment = []
        if preferred_labs is None:
            preferred_labs = []

        total_hours = (theory_hours if "Theory" in components else 0) + \
                      (practical_hours if "Practical" in components else 0) + \
                      (tutorial_hours if "Tutorial" in components else 0)

        data = {
            "id": new_id,
            "name": name.strip(),
            "type": ", ".join(components),
            "hours": total_hours,
            "class_id": class_id,
            "faculty_id": primary_faculty_id,
            "faculty_name": faculty_name,
            "primary_faculty_id": primary_faculty_id,
            "components": components,
            "academic_year": academic_year.strip(),
            "semester": semester.strip(),
            "theory_hours": int(theory_hours),
            "practical_hours": int(practical_hours),
            "tutorial_hours": int(tutorial_hours),
            "practical_faculty_pool": [int(x) for x in practical_faculty_pool],
            "tutorial_faculty_pool": [int(x) for x in tutorial_faculty_pool],
            "match_tutorial_batches": bool(match_tutorial_batches),
            "required_equipment": [str(e).strip() for e in required_equipment if str(e).strip()],
            "batch_size": int(batch_size or 20),
            "preferred_labs": [int(x) for x in preferred_labs if str(x).isdigit()]
        }

        if self.is_connected:
            self.db.collection("subjects").document(str(new_id)).set(data)
        else:
            self._local_data.setdefault("subjects", []).append(data)
            self._save_local_data()

        self.invalidate_cache()

        # Automatically allocate batch instructors based on defined components & eligible pools
        try:
            self.auto_allocate_subject_batches(new_id)
        except Exception as e:
            logger.warning(f"Error auto-allocating batches for subject {new_id}: {e}")

        return new_id

    def edit_subject(
        self,
        subject_id: int,
        name: str,
        components: List[str] = None,
        primary_faculty_id: int = None,
        theory_hours: int = 3,
        practical_hours: int = 2,
        tutorial_hours: int = 1,
        practical_faculty_pool: List[int] = None,
        tutorial_faculty_pool: List[int] = None,
        academic_year: str = None,
        semester: str = None,
        match_tutorial_batches: bool = True,
        required_equipment: List[str] = None,
        batch_size: int = None,
        preferred_labs: List[int] = None,
        # Legacy support
        sub_type: str = None,
        hours: int = None,
        faculty_id: int = None,
        class_id: int = None
    ):
        subject_id = int(subject_id)
        existing = self.get_subject(subject_id)
        if not existing:
            return

        if primary_faculty_id is None and faculty_id is not None:
            primary_faculty_id = int(faculty_id)
        if primary_faculty_id is None:
            primary_faculty_id = existing.get("primary_faculty_id") or existing.get("faculty_id")

        if class_id is None:
            class_id = existing.get("class_id")

        if components is None:
            if sub_type:
                components = ["Practical"] if "Practical" in sub_type else ["Theory"]
            else:
                components = existing.get("components", ["Theory"])

        if hours is not None:
            if "Practical" in components and "Theory" not in components:
                practical_hours = int(hours)
            else:
                theory_hours = int(hours)

        faculty_map = {f["id"]: f["name"] for f in self.get_faculty()}
        faculty_name = faculty_map.get(primary_faculty_id, "")

        if practical_faculty_pool is None:
            practical_faculty_pool = existing.get("practical_faculty_pool", [])
        if tutorial_faculty_pool is None:
            tutorial_faculty_pool = existing.get("tutorial_faculty_pool", [])
        if required_equipment is None:
            required_equipment = existing.get("required_equipment", [])
        if batch_size is None:
            batch_size = existing.get("batch_size", 20)
        if preferred_labs is None:
            preferred_labs = existing.get("preferred_labs", [])

        total_hours = (theory_hours if "Theory" in components else 0) + \
                      (practical_hours if "Practical" in components else 0) + \
                      (tutorial_hours if "Tutorial" in components else 0)

        update_data = {
            "name": name.strip(),
            "type": ", ".join(components),
            "hours": total_hours,
            "class_id": int(class_id) if class_id is not None else None,
            "faculty_id": primary_faculty_id,
            "faculty_name": faculty_name,
            "primary_faculty_id": primary_faculty_id,
            "components": components,
            "academic_year": (academic_year or existing.get("academic_year", "2024-2025")).strip(),
            "semester": (semester or existing.get("semester", "Semester 1")).strip(),
            "theory_hours": int(theory_hours),
            "practical_hours": int(practical_hours),
            "tutorial_hours": int(tutorial_hours),
            "practical_faculty_pool": [int(x) for x in practical_faculty_pool],
            "tutorial_faculty_pool": [int(x) for x in tutorial_faculty_pool],
            "match_tutorial_batches": bool(match_tutorial_batches),
            "required_equipment": [str(e).strip() for e in required_equipment if str(e).strip()],
            "batch_size": int(batch_size or 20),
            "preferred_labs": [int(x) for x in preferred_labs if str(x).isdigit()]
        }

        if self.is_connected:
            self.db.collection("subjects").document(str(subject_id)).update(update_data)
        else:
            for item in self._local_data.get("subjects", []):
                if item["id"] == subject_id:
                    item.update(update_data)
                    break
            self._save_local_data()

        self.invalidate_cache()

        # Update batch allocations for this subject
        try:
            self.auto_allocate_subject_batches(subject_id, override_existing=False)
        except Exception as e:
            logger.warning(f"Error updating allocations for subject {subject_id}: {e}")

    def delete_subject(self, subject_id: int):
        subject_id = int(subject_id)
        if self.is_connected:
            self.db.collection("subjects").document(str(subject_id)).delete()
            # Delete associated allocations
            alloc_docs = self.db.collection("faculty_allocations").where("subject_id", "==", subject_id).stream()
            for doc in alloc_docs:
                doc.reference.delete()
            # Delete associated legacy batch faculty
            bf_docs = self.db.collection("batch_faculty").where("subject_id", "==", subject_id).stream()
            for doc in bf_docs:
                doc.reference.delete()
        else:
            self._local_data["subjects"] = [
                s for s in self._local_data.get("subjects", [])
                if s["id"] != subject_id
            ]
            self._local_data["faculty_allocations"] = [
                a for a in self._local_data.get("faculty_allocations", [])
                if a.get("subject_id") != subject_id
            ]
            self._local_data["batch_faculty"] = [
                b for b in self._local_data.get("batch_faculty", [])
                if b.get("subject_id") != subject_id
            ]
            self._save_local_data()

        self.invalidate_cache()

    # =========================================================================
    # SUBJECT-SPECIFIC FACULTY MAPPINGS & BATCH ALLOCATION ENGINE
    # =========================================================================
    def get_faculty_allocations(self, class_id: Optional[int] = None, subject_id: Optional[int] = None, activity: Optional[str] = None) -> List[Record]:
        """
        Retrieves explicit mappings:
        Subject | Division | Activity (Theory/Practical/Tutorial) | Batch | Assigned Faculty | Assigned Laboratory
        """
        cache_key = f"faculty_allocations_{class_id}_{subject_id}_{activity}"
        if cache_key in self.cache:
            return self.cache[cache_key]

        tuple_keys = ["id", "subject_id", "class_id", "activity", "batch", "faculty_id", "faculty_name", "lab_id", "lab_name", "is_override"]
        records = []
        raw_items = []

        if self.is_connected:
            try:
                docs = self.db.collection("faculty_allocations").stream()
                for doc in docs:
                    d = doc.to_dict()
                    d["id"] = d.get("id", doc.id)
                    raw_items.append(d)
            except Exception as e:
                logger.warning(f"Firestore get_faculty_allocations error: {e}. Using local data.")
                raw_items = list(self._local_data.get("faculty_allocations", []))
        else:
            raw_items = list(self._local_data.get("faculty_allocations", []))

        # Initial seed if empty: migrate from existing subjects & batch_faculty
        if not raw_items:
            raw_items = self._seed_initial_allocations()

        faculty_map = {f["id"]: f["name"] for f in self.get_faculty()}
        rooms_map = {r["id"]: r["name"] for r in self.get_rooms()}

        for item in raw_items:
            d = dict(item)
            d["subject_id"] = int(d.get("subject_id", 0))
            d["class_id"] = int(d.get("class_id", 0))
            d["faculty_id"] = int(d.get("faculty_id", 0))
            d["activity"] = str(d.get("activity", "Theory")).strip()
            d["batch"] = str(d.get("batch", "All students")).strip()
            d["faculty_name"] = faculty_map.get(d["faculty_id"], d.get("faculty_name", "Unassigned"))
            raw_lab_id = d.get("lab_id")
            d["lab_id"] = int(raw_lab_id) if raw_lab_id is not None and str(raw_lab_id).isdigit() and int(raw_lab_id) > 0 else None
            d["lab_name"] = rooms_map.get(d["lab_id"], d.get("lab_name", "")) if d["lab_id"] else ""
            d["is_override"] = bool(d.get("is_override", False))

            if class_id is not None and d["class_id"] != int(class_id):
                continue
            if subject_id is not None and d["subject_id"] != int(subject_id):
                continue
            if activity is not None and d["activity"].lower() != activity.lower():
                continue

            records.append(Record(d, tuple_keys))

        # Order by subject_id, activity (Theory first, then Practical, then Tutorial), batch
        activity_order = {"Theory": 1, "Practical": 2, "Tutorial": 3}
        records.sort(key=lambda r: (r["class_id"], r["subject_id"], activity_order.get(r["activity"], 99), r["batch"]))

        self.cache[cache_key] = records
        return records

    def _seed_initial_allocations(self) -> List[Dict[str, Any]]:
        """
        Seeds initial faculty_allocations table from current subjects, batch_faculty, and compatible labs.
        """
        subjects = self.get_subjects()
        batch_faculty = self.get_batch_faculty()
        faculty_map = {f["id"]: f["name"] for f in self.get_faculty()}
        seeded = []

        # Map batch faculty by (class_id, subject_id, batch)
        bf_map = {(b["class_id"], b["subject_id"], b["batch"]): b["faculty_id"] for b in batch_faculty}

        for sub in subjects:
            cid = sub["class_id"]
            sid = sub["id"]
            components = sub.get("components", ["Theory"])
            primary_fid = sub.get("primary_faculty_id") or sub.get("faculty_id")

            if "Theory" in components and primary_fid:
                alloc_id = f"{cid}_{sid}_Theory_All_students"
                seeded.append({
                    "id": alloc_id,
                    "class_id": cid,
                    "subject_id": sid,
                    "activity": "Theory",
                    "batch": "All students",
                    "faculty_id": primary_fid,
                    "faculty_name": faculty_map.get(primary_fid, ""),
                    "lab_id": None,
                    "lab_name": "",
                    "is_override": False
                })

            if "Practical" in components:
                compatible_labs = self.get_compatible_labs_for_subject(sid)
                for b_idx, b_name in enumerate(["A1", "A2", "A3", "A4"]):
                    fid = bf_map.get((cid, sid, b_name), primary_fid)
                    chosen_lab = compatible_labs[b_idx % len(compatible_labs)] if compatible_labs else None
                    chosen_lab_id = chosen_lab["id"] if chosen_lab else None
                    chosen_lab_name = chosen_lab["name"] if chosen_lab else ""
                    if fid:
                        alloc_id = f"{cid}_{sid}_Practical_{b_name}"
                        seeded.append({
                            "id": alloc_id,
                            "class_id": cid,
                            "subject_id": sid,
                            "activity": "Practical",
                            "batch": b_name,
                            "faculty_id": fid,
                            "faculty_name": faculty_map.get(fid, ""),
                            "lab_id": chosen_lab_id,
                            "lab_name": chosen_lab_name,
                            "is_override": False
                        })

            if "Tutorial" in components:
                for b_name in ["A1", "A2", "A3", "A4"]:
                    fid = primary_fid
                    if fid:
                        alloc_id = f"{cid}_{sid}_Tutorial_{b_name}"
                        seeded.append({
                            "id": alloc_id,
                            "class_id": cid,
                            "subject_id": sid,
                            "activity": "Tutorial",
                            "batch": b_name,
                            "faculty_id": fid,
                            "faculty_name": faculty_map.get(fid, ""),
                            "lab_id": None,
                            "lab_name": "",
                            "is_override": False
                        })

        # Save to database
        if self.is_connected:
            batch = self.db.batch()
            for idx, item in enumerate(seeded):
                ref = self.db.collection("faculty_allocations").document(item["id"])
                batch.set(ref, item)
                if (idx + 1) % 400 == 0:
                    batch.commit()
                    batch = self.db.batch()
            batch.commit()
        else:
            self._local_data["faculty_allocations"] = list(seeded)
            self._save_local_data()

        return seeded

    def save_faculty_allocation(
        self,
        subject_id: int,
        class_id: int,
        activity: str,
        batch: str,
        faculty_id: int,
        lab_id: Optional[int] = None,
        is_override: bool = True
    ):
        """
        Explicitly saves or updates a single batch assignment with faculty and laboratory mapping.
        Triggers workload and conflict updates.
        """
        subject_id = int(subject_id)
        class_id = int(class_id)
        faculty_id = int(faculty_id)
        activity = activity.strip()
        batch = batch.strip()
        clean_lab_id = int(lab_id) if lab_id is not None and str(lab_id).isdigit() and int(lab_id) > 0 else None

        alloc_id = f"{class_id}_{subject_id}_{activity}_{batch.replace(' ', '_')}"
        faculty_map = {f["id"]: f["name"] for f in self.get_faculty()}
        faculty_name = faculty_map.get(faculty_id, "")

        rooms_map = {r["id"]: r["name"] for r in self.get_rooms()}
        lab_name = rooms_map.get(clean_lab_id, "") if clean_lab_id else ""

        data = {
            "id": alloc_id,
            "subject_id": subject_id,
            "class_id": class_id,
            "activity": activity,
            "batch": batch,
            "faculty_id": faculty_id,
            "faculty_name": faculty_name,
            "lab_id": clean_lab_id,
            "lab_name": lab_name,
            "is_override": is_override,
            "updated_at": datetime.utcnow().isoformat()
        }

        if self.is_connected:
            self.db.collection("faculty_allocations").document(alloc_id).set(data)
        else:
            self._local_data["faculty_allocations"] = [
                a for a in self._local_data.get("faculty_allocations", [])
                if a.get("id") != alloc_id
            ]
            self._local_data["faculty_allocations"].append(data)
            self._save_local_data()

        # Synchronize with legacy batch_faculty if Practical
        if activity == "Practical":
            self._sync_practical_to_batch_faculty(class_id, subject_id, batch, faculty_id)

        self.invalidate_cache()

    def _sync_practical_to_batch_faculty(self, class_id: int, subject_id: int, batch: str, faculty_id: int):
        """Maintains backwards compatibility for batch_faculty collection."""
        if self.is_connected:
            query = self.db.collection("batch_faculty").where("class_id", "==", class_id).where("subject_id", "==", subject_id).where("batch", "==", batch)
            found = False
            for doc in query.stream():
                doc.reference.update({"faculty_id": faculty_id})
                found = True
            if not found:
                doc_ref = self.db.collection("batch_faculty").document()
                doc_ref.set({
                    "id": doc_ref.id,
                    "class_id": class_id,
                    "subject_id": subject_id,
                    "batch": batch,
                    "faculty_id": faculty_id
                })
        else:
            existing = False
            for bf in self._local_data.get("batch_faculty", []):
                if bf["class_id"] == class_id and bf["subject_id"] == subject_id and bf["batch"] == batch:
                    bf["faculty_id"] = faculty_id
                    existing = True
                    break
            if not existing:
                next_id = max([b.get("id", 0) for b in self._local_data.get("batch_faculty", [])], default=0) + 1
                self._local_data.setdefault("batch_faculty", []).append({
                    "id": next_id,
                    "class_id": class_id,
                    "subject_id": subject_id,
                    "batch": batch,
                    "faculty_id": faculty_id
                })
            self._save_local_data()

    def auto_allocate_subject_batches(self, subject_id: int, override_existing: bool = False) -> Dict[str, Any]:
        """
        Smart Automatic Batch Allocation Engine.
        Allocates faculty and compatible laboratories across practical & tutorial batches based on:
        - Subject-specific eligibility pool
        - Faculty availability & current workload balance
        - Compatible laboratories matching batch size, equipment, and supported subjects
        - Avoiding assigning primary faculty to all practical batches when other eligible faculty exist
        - Strict subject-specific restriction for tutorials
        """
        subject = self.get_subject(subject_id)
        if not subject:
            return {"success": False, "message": "Subject not found"}

        class_id = subject["class_id"]
        components = subject.get("components", ["Theory"])
        primary_id = subject.get("primary_faculty_id") or subject.get("faculty_id")
        prac_pool = list(subject.get("practical_faculty_pool", []))
        tut_pool = list(subject.get("tutorial_faculty_pool", []))
        batches = ["A1", "A2", "A3", "A4"]

        # Current allocations for checking override status
        existing_allocs = {
            (a["activity"], a["batch"]): a
            for a in self.get_faculty_allocations(class_id=class_id, subject_id=subject_id)
        }

        # Calculate current faculty workloads to inform balanced distribution
        workloads = self.calculate_faculty_workload()

        # -------------------------------------------------------------
        # 1. THEORY COMPONENT (Primary Faculty lead)
        # -------------------------------------------------------------
        if "Theory" in components and primary_id:
            curr = existing_allocs.get(("Theory", "All students"))
            if not curr or not curr.get("is_override") or override_existing:
                self.save_faculty_allocation(
                    subject_id=subject_id,
                    class_id=class_id,
                    activity="Theory",
                    batch="All students",
                    faculty_id=primary_id,
                    lab_id=None,
                    is_override=False
                )

        # -------------------------------------------------------------
        # 2. PRACTICAL COMPONENT (Batches A1, A2, A3, A4 & Compatible Labs)
        # -------------------------------------------------------------
        if "Practical" in components:
            # Candidate pool: practical_faculty_pool
            candidates = [fid for fid in prac_pool if fid]
            if not candidates and primary_id:
                candidates = [primary_id]

            # If candidates contain non-primary faculty, prioritize non-primary first
            non_primary_candidates = [fid for fid in candidates if fid != primary_id]
            eligible_pool = non_primary_candidates if non_primary_candidates else candidates

            # Sort eligible pool by current workload ascending for fair distribution
            eligible_pool.sort(key=lambda fid: workloads.get(fid, {}).get("total_hours", 0))

            # Ensure at least 4 distinct faculty in pool for concurrent batches A1-A4
            if len(eligible_pool) < 4:
                all_fac_sorted = sorted([f["id"] for f in self.get_faculty()], key=lambda fid: workloads.get(fid, {}).get("total_hours", 0))
                for f_id in all_fac_sorted:
                    if f_id not in eligible_pool:
                        eligible_pool.append(f_id)
                        if len(eligible_pool) == 4:
                            break

            # Identify suitable compatible laboratories
            compatible_labs = self.get_compatible_labs_for_subject(subject_id)

            for idx, batch_name in enumerate(batches):
                curr = existing_allocs.get(("Practical", batch_name))
                if curr and curr.get("is_override") and not override_existing:
                    continue

                # Round-robin allocation among eligible pool
                chosen_faculty = eligible_pool[idx % len(eligible_pool)]
                chosen_lab = compatible_labs[idx % len(compatible_labs)] if compatible_labs else None
                chosen_lab_id = chosen_lab["id"] if chosen_lab else None

                self.save_faculty_allocation(
                    subject_id=subject_id,
                    class_id=class_id,
                    activity="Practical",
                    batch=batch_name,
                    faculty_id=chosen_faculty,
                    lab_id=chosen_lab_id,
                    is_override=False
                )

        # -------------------------------------------------------------
        # 3. TUTORIAL COMPONENT (Strictly subject-specific eligibility)
        # -------------------------------------------------------------
        if "Tutorial" in components:
            tut_candidates = [fid for fid in tut_pool if fid]
            if not tut_candidates and primary_id:
                tut_candidates = [primary_id]

            tut_candidates.sort(key=lambda fid: workloads.get(fid, {}).get("total_hours", 0))

            target_batches = batches if subject.get("match_tutorial_batches", True) else ["All students"]
            for idx, batch_name in enumerate(target_batches):
                curr = existing_allocs.get(("Tutorial", batch_name))
                if curr and curr.get("is_override") and not override_existing:
                    continue

                chosen_faculty = tut_candidates[idx % len(tut_candidates)]
                self.save_faculty_allocation(
                    subject_id=subject_id,
                    class_id=class_id,
                    activity="Tutorial",
                    batch=batch_name,
                    faculty_id=chosen_faculty,
                    is_override=False
                )

        self.invalidate_cache()
        return {"success": True, "message": f"Allocations configured for {subject['name']}"}

    # =========================================================================
    # WORKLOAD MANAGEMENT INTEGRATION
    # =========================================================================
    def calculate_faculty_workload(self) -> Dict[int, Dict[str, Any]]:
        """
        Calculates separate and total workload for every faculty member:
        - Theory hours
        - Practical hours (per batch)
        - Tutorial hours (per batch)
        - Status (Normal, Optimal, Overloaded) against max hours limit (default 24)
        """
        faculty = self.get_faculty()
        subjects_map = {s["id"]: s for s in self.get_subjects(fetch_faculty_names=False)}
        classes_map = {c["id"]: c["name"] for c in self.get_classes()}
        allocations = self.get_faculty_allocations()

        workloads = {}
        for f in faculty:
            fid = f["id"]
            max_limit = int(f.get("max_hours") or 24)
            workloads[fid] = {
                "faculty_id": fid,
                "name": f["name"],
                "theory_hours": 0,
                "practical_hours": 0,
                "tutorial_hours": 0,
                "total_hours": 0,
                "max_hours": max_limit,
                "utilization": 0.0,
                "status": "Normal",
                "assignments": []
            }

        for alloc in allocations:
            fid = alloc["faculty_id"]
            if fid not in workloads:
                continue

            sub = subjects_map.get(alloc["subject_id"])
            if not sub:
                continue

            cname = classes_map.get(alloc["class_id"], f"Class {alloc['class_id']}")
            act = alloc["activity"]
            batch = alloc["batch"]

            hours = 0
            if act == "Theory":
                hours = int(sub.get("theory_hours", sub.get("hours", 3)))
                workloads[fid]["theory_hours"] += hours
            elif act == "Practical":
                hours = int(sub.get("practical_hours", 2))
                workloads[fid]["practical_hours"] += hours
            elif act == "Tutorial":
                hours = int(sub.get("tutorial_hours", 1))
                workloads[fid]["tutorial_hours"] += hours

            workloads[fid]["assignments"].append({
                "subject_id": sub["id"],
                "subject_name": sub["name"],
                "class_name": cname,
                "activity": act,
                "batch": batch,
                "hours": hours,
                "is_override": alloc.get("is_override", False)
            })

        for fid, w in workloads.items():
            tot = w["theory_hours"] + w["practical_hours"] + w["tutorial_hours"]
            w["total_hours"] = tot
            max_h = w["max_hours"]
            w["utilization"] = round((tot / max_h * 100), 1) if max_h > 0 else 0.0

            if tot > max_h:
                w["status"] = "Overloaded"
            elif tot >= (max_h - 4):
                w["status"] = "Optimal"
            else:
                w["status"] = "Normal"

        return workloads

    def calculate_workload_equality_metrics(self, workloads: Optional[Dict[int, Dict[str, Any]]] = None) -> Dict[str, Any]:
        """
        Computes institutional workload equality and balance KPI metrics across all faculty:
        - Total institutional teaching hours
        - Mean workload per faculty (target balance line)
        - Min and max faculty loads
        - Workload spread / disparity (max - min)
        - Standard deviation (sigma) of workload distribution
        - Workload equality rating (Optimal, Good, Moderate, Uneven)
        """
        if workloads is None:
            workloads = self.calculate_faculty_workload()

        loads = [w["total_hours"] for w in workloads.values()]
        faculty_count = len(loads)
        if faculty_count == 0:
            return {
                "faculty_count": 0,
                "total_hours": 0,
                "mean_load": 0.0,
                "min_load": 0,
                "max_load": 0,
                "disparity": 0,
                "std_dev": 0.0,
                "is_balanced": True,
                "quality_label": "N/A",
                "badge_class": "secondary"
            }

        total_hours = sum(loads)
        mean_load = round(total_hours / faculty_count, 1)
        min_load = min(loads)
        max_load = max(loads)
        disparity = max_load - min_load
        variance = sum((x - mean_load) ** 2 for x in loads) / faculty_count
        std_dev = round(math.sqrt(variance), 2)

        if disparity <= 2:
            quality_label = "Optimal / Highly Balanced"
            is_balanced = True
            badge_class = "success"
        elif disparity <= 4:
            quality_label = "Good Balance"
            is_balanced = True
            badge_class = "primary"
        elif disparity <= 8:
            quality_label = "Moderate Disparity"
            is_balanced = False
            badge_class = "warning"
        else:
            quality_label = "High Disparity (Unequal)"
            is_balanced = False
            badge_class = "danger"

        return {
            "faculty_count": faculty_count,
            "total_hours": total_hours,
            "mean_load": mean_load,
            "min_load": min_load,
            "max_load": max_load,
            "disparity": disparity,
            "std_dev": std_dev,
            "is_balanced": is_balanced,
            "quality_label": quality_label,
            "badge_class": badge_class
        }

    def equalize_faculty_workloads(self, respect_overrides: bool = True) -> Dict[str, Any]:
        """
        Intelligent Automated Workload Equalizer & Fair Distribution Engine.
        Automatically distributes total institutional teaching load (Theory, Practical Batches A1-A4, Tutorials)
        equally among all faculty members.
        - Respects manual overrides if respect_overrides=True
        - Fairly assigns Theory lectures with preference to subject lead if under target mean
        - Maps 4 distinct faculty members across concurrent practical batches (A1-A4) with compatible labs
        - Distributes tutorial batches across eligible pools
        - Runs iterative swap optimization between highest-loaded and lowest-loaded faculty to achieve disparity <= 2h
        - Updates Firestore and local collections atomically
        """
        faculty = self.get_faculty()
        subjects = self.get_subjects(fetch_faculty_names=False)
        allocations = self.get_faculty_allocations()

        faculty_ids = [f["id"] for f in faculty]
        faculty_map = {f["id"]: f["name"] for f in faculty}

        running_loads = {fid: 0 for fid in faculty_ids}
        new_allocations = []
        allocated_keys = set()

        # 1. Respect manual overrides if enabled
        if respect_overrides:
            for a in allocations:
                if a.get("is_override"):
                    sub = next((s for s in subjects if s["id"] == a["subject_id"]), None)
                    hrs = 0
                    if sub:
                        act = a["activity"]
                        if act == "Theory":
                            hrs = int(sub.get("theory_hours") or sub.get("hours", 3))
                        elif act == "Practical":
                            hrs = int(sub.get("practical_hours", 2))
                        elif act == "Tutorial":
                            hrs = int(sub.get("tutorial_hours", 1))
                    fid = a["faculty_id"]
                    if fid in running_loads:
                        running_loads[fid] += hrs
                    key = (a["class_id"], a["subject_id"], a["activity"], a["batch"])
                    allocated_keys.add(key)
                    new_allocations.append(dict(a))

        # Target mean load for institution
        total_estimated_hrs = 0
        for sub in subjects:
            comps = sub.get("components", ["Theory"])
            if "Theory" in comps:
                total_estimated_hrs += int(sub.get("theory_hours") or sub.get("hours", 3))
            if "Practical" in comps:
                total_estimated_hrs += int(sub.get("practical_hours", 2)) * 4
            if "Tutorial" in comps:
                batch_count = 4 if sub.get("match_tutorial_batches", True) else 1
                total_estimated_hrs += int(sub.get("tutorial_hours", 1)) * batch_count
        target_mean = round(total_estimated_hrs / len(faculty_ids), 1) if faculty_ids else 22.5

        # 2. Theory Allocation
        for sub in subjects:
            cid = sub["class_id"]
            sid = sub["id"]
            components = sub.get("components", ["Theory"])
            if "Theory" not in components:
                continue
            key = (cid, sid, "Theory", "All students")
            if key in allocated_keys:
                continue

            th_hrs = int(sub.get("theory_hours") or sub.get("hours", 3))
            primary_id = sub.get("primary_faculty_id") or sub.get("faculty_id")

            sorted_by_load = sorted(faculty_ids, key=lambda f: running_loads[f])
            if primary_id and primary_id in running_loads and (running_loads[primary_id] + th_hrs <= target_mean):
                chosen_fid = primary_id
            else:
                chosen_fid = sorted_by_load[0]

            running_loads[chosen_fid] += th_hrs
            allocated_keys.add(key)
            new_allocations.append({
                "id": f"{cid}_{sid}_Theory_All_students",
                "class_id": cid,
                "subject_id": sid,
                "activity": "Theory",
                "batch": "All students",
                "faculty_id": chosen_fid,
                "faculty_name": faculty_map.get(chosen_fid, ""),
                "lab_id": None,
                "lab_name": "",
                "is_override": False,
                "updated_at": datetime.utcnow().isoformat()
            })

        # 3. Practical Batches Allocation (A1, A2, A3, A4 & Compatible Labs)
        for sub in subjects:
            cid = sub["class_id"]
            sid = sub["id"]
            components = sub.get("components", [])
            if "Practical" not in components:
                continue

            prac_hrs = int(sub.get("practical_hours", 2))
            prac_pool = [fid for fid in sub.get("practical_faculty_pool", []) if fid in running_loads]
            compatible_labs = self.get_compatible_labs_for_subject(sid, sub.get("batch_size", 20))

            if len(prac_pool) >= 4:
                cand_pool = list(prac_pool)
            else:
                cand_pool = list(faculty_ids)

            cand_pool.sort(key=lambda f: running_loads[f])
            selected_facs = []
            for f in cand_pool:
                if f not in selected_facs:
                    selected_facs.append(f)
                    if len(selected_facs) == 4:
                        break
            if len(selected_facs) < 4:
                for f in sorted(faculty_ids, key=lambda f: running_loads[f]):
                    if f not in selected_facs:
                        selected_facs.append(f)
                        if len(selected_facs) == 4:
                            break

            batches = ["A1", "A2", "A3", "A4"]
            for b_idx, b_name in enumerate(batches):
                key = (cid, sid, "Practical", b_name)
                if key in allocated_keys:
                    continue

                chosen_fid = selected_facs[b_idx % len(selected_facs)]
                running_loads[chosen_fid] += prac_hrs
                allocated_keys.add(key)

                chosen_lab = compatible_labs[b_idx % len(compatible_labs)] if compatible_labs else None
                chosen_lab_id = chosen_lab["id"] if chosen_lab else None
                chosen_lab_name = chosen_lab["name"] if chosen_lab else ""

                new_allocations.append({
                    "id": f"{cid}_{sid}_Practical_{b_name}",
                    "class_id": cid,
                    "subject_id": sid,
                    "activity": "Practical",
                    "batch": b_name,
                    "faculty_id": chosen_fid,
                    "faculty_name": faculty_map.get(chosen_fid, ""),
                    "lab_id": chosen_lab_id,
                    "lab_name": chosen_lab_name,
                    "is_override": False,
                    "updated_at": datetime.utcnow().isoformat()
                })

        # 4. Tutorial Batches Allocation
        for sub in subjects:
            cid = sub["class_id"]
            sid = sub["id"]
            components = sub.get("components", [])
            if "Tutorial" not in components:
                continue

            tut_hrs = int(sub.get("tutorial_hours", 1))
            tut_pool = [fid for fid in sub.get("tutorial_faculty_pool", []) if fid in running_loads]
            if len(tut_pool) < 2:
                tut_pool = list(faculty_ids)

            target_batches = ["A1", "A2", "A3", "A4"] if sub.get("match_tutorial_batches", True) else ["All students"]
            for b_name in target_batches:
                key = (cid, sid, "Tutorial", b_name)
                if key in allocated_keys:
                    continue

                tut_pool.sort(key=lambda f: running_loads[f])
                chosen_fid = tut_pool[0]
                running_loads[chosen_fid] += tut_hrs
                allocated_keys.add(key)

                new_allocations.append({
                    "id": f"{cid}_{sid}_Tutorial_{b_name.replace(' ', '_')}",
                    "class_id": cid,
                    "subject_id": sid,
                    "activity": "Tutorial",
                    "batch": b_name,
                    "faculty_id": chosen_fid,
                    "faculty_name": faculty_map.get(chosen_fid, ""),
                    "lab_id": None,
                    "lab_name": "",
                    "is_override": False,
                    "updated_at": datetime.utcnow().isoformat()
                })

        # 5. Iterative Swap Optimization Engine
        for _ in range(300):
            max_fid = max(faculty_ids, key=lambda f: running_loads[f])
            min_fid = min(faculty_ids, key=lambda f: running_loads[f])

            if running_loads[max_fid] - running_loads[min_fid] <= 1:
                break

            swapped = False
            for a in new_allocations:
                if a.get("is_override") or a["faculty_id"] != max_fid:
                    continue

                act = a["activity"]
                hrs = 2 if act == "Practical" else (1 if act == "Tutorial" else 3)
                current_diff = running_loads[max_fid] - running_loads[min_fid]
                new_diff = abs((running_loads[max_fid] - hrs) - (running_loads[min_fid] + hrs))

                if new_diff < current_diff:
                    if act == "Practical":
                        cid = a["class_id"]
                        sid = a["subject_id"]
                        other_batches = [
                            x["faculty_id"] for x in new_allocations
                            if x["class_id"] == cid and x["subject_id"] == sid and x["activity"] == "Practical" and x["batch"] != a["batch"]
                        ]
                        if min_fid in other_batches:
                            continue

                    a["faculty_id"] = min_fid
                    a["faculty_name"] = faculty_map.get(min_fid, "")
                    running_loads[max_fid] -= hrs
                    running_loads[min_fid] += hrs
                    swapped = True
                    break

            if not swapped:
                break

        # 6. Save Equalized Allocations to Database
        if self.is_connected:
            existing_doc_refs = list(self.db.collection("faculty_allocations").stream())
            new_doc_ids = set(item["id"] for item in new_allocations)

            # Delete stale or duplicate allocation documents
            del_batch = self.db.batch()
            del_count = 0
            for doc in existing_doc_refs:
                if doc.id not in new_doc_ids:
                    del_batch.delete(doc.reference)
                    del_count += 1
                    if del_count % 400 == 0:
                        del_batch.commit()
                        del_batch = self.db.batch()
            if del_count > 0:
                del_batch.commit()

            # Set new equalized allocations
            batch = self.db.batch()
            for idx, item in enumerate(new_allocations):
                ref = self.db.collection("faculty_allocations").document(item["id"])
                batch.set(ref, item)
                if (idx + 1) % 400 == 0:
                    batch.commit()
                    batch = self.db.batch()
            batch.commit()

            # Batch sync practical allocations to batch_faculty in one pass
            bf_docs = {
                (d.to_dict().get("class_id"), d.to_dict().get("subject_id"), d.to_dict().get("batch")): d.reference
                for d in self.db.collection("batch_faculty").stream()
            }
            bf_batch = self.db.batch()
            bf_count = 0
            for a in new_allocations:
                if a["activity"] == "Practical":
                    key = (a["class_id"], a["subject_id"], a["batch"])
                    if key in bf_docs:
                        bf_batch.update(bf_docs[key], {"faculty_id": a["faculty_id"]})
                    else:
                        new_ref = self.db.collection("batch_faculty").document()
                        bf_batch.set(new_ref, {
                            "id": new_ref.id,
                            "class_id": a["class_id"],
                            "subject_id": a["subject_id"],
                            "batch": a["batch"],
                            "faculty_id": a["faculty_id"]
                        })
                    bf_count += 1
                    if bf_count % 400 == 0:
                        bf_batch.commit()
                        bf_batch = self.db.batch()
            if bf_count > 0:
                bf_batch.commit()
        else:
            self._local_data["faculty_allocations"] = list(new_allocations)
            self._save_local_data()
            for a in new_allocations:
                if a["activity"] == "Practical":
                    self._sync_practical_to_batch_faculty(a["class_id"], a["subject_id"], a["batch"], a["faculty_id"])

        self.invalidate_cache()

        # 7. Compute results
        after_loads = list(running_loads.values())
        tot = sum(after_loads)
        mean_load = round(tot / len(after_loads), 1) if after_loads else 0.0
        min_l = min(after_loads) if after_loads else 0
        max_l = max(after_loads) if after_loads else 0
        disparity = max_l - min_l
        std_dev = round(math.sqrt(sum((x - mean_load) ** 2 for x in after_loads) / len(after_loads)), 2) if after_loads else 0.0

        return {
            "success": True,
            "faculty_count": len(faculty_ids),
            "total_hours": tot,
            "mean_load": mean_load,
            "min_load": min_l,
            "max_load": max_l,
            "disparity": disparity,
            "std_dev": std_dev,
            "loads": running_loads,
            "allocations_count": len(new_allocations)
        }

    # =========================================================================
    # PRE-TIMETABLE GENERATION VALIDATION
    # =========================================================================
    def validate_timetable_readiness(self) -> Dict[str, Any]:
        """
        Verifies scheduling readiness before timetable generation:
        1. All subjects and batches have assigned faculty.
        2. No faculty member exceeds their workload limit.
        3. All assignments adhere to subject eligibility rules.
        4. Adequate laboratory and classroom capacity exists.
        """
        subjects = self.get_subjects()
        classes = self.get_classes()
        rooms = self.get_rooms()
        workloads = self.calculate_faculty_workload()
        allocations = self.get_faculty_allocations()

        alloc_map = {
            (a["subject_id"], a["activity"], a["batch"]): a["faculty_id"]
            for a in allocations
        }

        errors = []
        warnings = []
        classes_map = {c["id"]: c["name"] for c in classes}

        # 1. Completeness & Eligibility check
        for sub in subjects:
            sid = sub["id"]
            cid = sub["class_id"]
            cname = classes_map.get(cid, f"Class {cid}")
            components = sub.get("components", ["Theory"])

            # Theory
            if "Theory" in components:
                f_id = alloc_map.get((sid, "Theory", "All students"))
                if not f_id:
                    errors.append(f"Missing Theory faculty for {sub['name']} ({cname})")

            # Practical
            if "Practical" in components:
                prac_pool = set(sub.get("practical_faculty_pool", []))
                primary_id = sub.get("primary_faculty_id")
                if primary_id:
                    prac_pool.add(primary_id)

                for b in ["A1", "A2", "A3", "A4"]:
                    f_id = alloc_map.get((sid, "Practical", b))
                    if not f_id:
                        errors.append(f"Unassigned Practical batch: {sub['name']} ({cname}) - Batch {b}")
                    elif len(prac_pool) >= 4 and f_id not in prac_pool:
                        warnings.append(f"Batch {b} for {sub['name']} assigned to faculty #{f_id} outside authorized pool.")

            # Tutorial
            if "Tutorial" in components:
                tut_pool = set(sub.get("tutorial_faculty_pool", []))
                primary_id = sub.get("primary_faculty_id")
                if primary_id:
                    tut_pool.add(primary_id)

                target_batches = ["A1", "A2", "A3", "A4"] if sub.get("match_tutorial_batches", True) else ["All students"]
                for b in target_batches:
                    f_id = alloc_map.get((sid, "Tutorial", b))
                    if not f_id:
                        errors.append(f"Unassigned Tutorial batch: {sub['name']} ({cname}) - Batch {b}")
                    elif len(tut_pool) >= 2 and f_id not in tut_pool:
                        warnings.append(f"Tutorial batch {b} for {sub['name']} assigned to faculty #{f_id} outside authorized pool.")

        # 2. Workload Compliance
        for fid, w in workloads.items():
            if w["status"] == "Overloaded":
                warnings.append(f"Faculty {w['name']} exceeds max workload ({w['total_hours']}h / {w['max_hours']}h max limit).")

        # 3. Room & Facility Capacity & Lab Compatibility
        labs = [r for r in rooms if r.get("type") == "Lab"]
        classrooms = [r for r in rooms if r.get("type") == "Classroom"]
        if len(labs) < 4:
            warnings.append(f"Only {len(labs)} laboratories detected. Minimum 4 labs recommended for concurrent 4-batch practicals.")
        if len(classrooms) < len(classes):
            warnings.append(f"Only {len(classrooms)} classrooms for {len(classes)} classes. Room sharing may be constrained.")

        # Laboratory-specific readiness: check practical subjects have compatible labs
        for sub in subjects:
            if "Practical" in sub.get("components", []):
                compat_labs = self.get_compatible_labs_for_subject(sub["id"], sub.get("batch_size", 20))
                if not compat_labs:
                    errors.append(f"No compatible laboratory found for {sub['name']} (Batch size: {sub.get('batch_size', 20)}, Equipment: {', '.join(sub.get('required_equipment', [])) or 'Standard'}).")

        # Check laboratory maintenance blocks
        for lab in labs:
            maint_count = len(lab.get("available_slots", []))
            if maint_count >= 20:
                warnings.append(f"Laboratory {lab['name']} has {maint_count}/30 periods blocked for maintenance; scheduling may be heavily constrained.")

        return {
            "is_ready": len(errors) == 0,
            "ready": len(errors) == 0,
            "errors": errors,
            "warnings": warnings,
            "issues": errors + warnings,
            "total_subjects": len(subjects),
            "total_allocations": len(allocations),
            "overloaded_count": sum(1 for w in workloads.values() if w["status"] == "Overloaded")
        }

    def calculate_laboratory_utilization(self, timetable_data: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """
        Calculates weekly utilization statistics for each laboratory based on the timetable:
        - Total available operating slots (30 standard slots minus maintenance/downtime)
        - Booked practical/tutorial/lecture hours
        - Utilization percentage
        - Operating status ('High Load', 'Optimal', 'Underutilized', 'Maintenance Heavy')
        - Breakdown of scheduled sessions
        """
        if timetable_data is None:
            working = self.get_working_timetable()
            timetable_data = working.get("data", {})

        labs = self.get_labs()
        lab_reports = []
        total_capacity = 0
        total_booked = 0

        day_names = ["Mon", "Tue", "Wed", "Thu", "Fri"]

        for lab in labs:
            lab_id = lab["id"]
            lab_name = lab["name"]
            code = lab.get("code") or f"LAB-{lab_id:02d}"
            dept = lab.get("department", "Computer Science & Engineering")
            cap = lab.get("capacity", 30)
            equip = lab.get("equipment", [])
            supp_subs = lab.get("supported_subjects", [])
            maint_slots = list(lab.get("available_slots", []))
            maint_count = len(maint_slots)

            # Operating capacity: 30 slots (5 days x 6 periods) minus maintenance downtime
            operating_slots = max(1, 30 - maint_count)
            total_capacity += operating_slots

            # Fetch schedule matrix
            schedule = self.get_room_schedule(lab_name, timetable_data)
            booked_slots = 0
            sessions = []

            for d_idx in range(5):
                for p_idx in range(6):
                    events = schedule[d_idx][p_idx]
                    if events:
                        booked_slots += 1
                        for ev in events:
                            sessions.append({
                                "day": day_names[d_idx],
                                "period": p_idx + 1,
                                "class": ev.get("class", ""),
                                "batch": ev.get("batch", ""),
                                "text": ev.get("text", ""),
                                "type": ev.get("type", "Practical")
                            })

            total_booked += booked_slots
            utilization = round((booked_slots / operating_slots) * 100, 1)

            if maint_count >= 15:
                status = "Maintenance Heavy"
            elif utilization >= 75.0:
                status = "High Load"
            elif utilization >= 30.0:
                status = "Optimal"
            else:
                status = "Underutilized"

            lab_reports.append({
                "id": lab_id,
                "name": lab_name,
                "code": code,
                "department": dept,
                "capacity": cap,
                "equipment": equip,
                "supported_subjects": supp_subs,
                "maintenance_slots": maint_slots,
                "maintenance_count": maint_count,
                "operating_capacity": operating_slots,
                "booked_hours": booked_slots,
                "utilization": utilization,
                "status": status,
                "sessions": sessions
            })

        avg_util = round((total_booked / total_capacity * 100), 1) if total_capacity > 0 else 0.0

        return {
            "summary": {
                "total_labs": len(labs),
                "total_operating_capacity": total_capacity,
                "total_booked_hours": total_booked,
                "average_utilization": avg_util,
                "high_load_count": sum(1 for r in lab_reports if r["status"] == "High Load"),
                "optimal_count": sum(1 for r in lab_reports if r["status"] == "Optimal"),
                "underutilized_count": sum(1 for r in lab_reports if r["status"] == "Underutilized"),
                "maintenance_heavy_count": sum(1 for r in lab_reports if r["status"] == "Maintenance Heavy")
            },
            "labs": lab_reports
        }

    # =========================================================================
    # BATCH FACULTY (Legacy Compatibility Access)
    # =========================================================================
    def get_batch_faculty(self) -> List[Record]:
        cache_key = "batch_faculty"
        if cache_key in self.cache:
            return self.cache[cache_key]

        tuple_keys = ["id", "class_id", "subject_id", "batch", "faculty_id"]
        records = []
        if self.is_connected:
            try:
                docs = self.db.collection("batch_faculty").stream()
                for doc in docs:
                    d = doc.to_dict()
                    d["id"] = int(d.get("id", doc.id))
                    records.append(Record(d, tuple_keys))
            except Exception as e:
                logger.warning(f"Firestore get_batch_faculty error: {e}. Using local data.")
                for item in self._local_data.get("batch_faculty", []):
                    records.append(Record(dict(item), tuple_keys))
        else:
            for item in self._local_data.get("batch_faculty", []):
                records.append(Record(dict(item), tuple_keys))

        records.sort(key=lambda r: r["id"])
        self.cache[cache_key] = records
        return records

    def assign_batch_faculty(self, class_id: int, subject_id: int, batch_assignments: Dict[str, int]):
        """
        Assigns faculty for batches (A1, A2, A3, A4) for a given class and subject.
        Removes existing assignments for (class_id, subject_id) first.
        """
        class_id = int(class_id)
        subject_id = int(subject_id)

        if self.is_connected:
            # Delete old assignments
            query = self.db.collection("batch_faculty").where("class_id", "==", class_id).where("subject_id", "==", subject_id)
            for doc in query.stream():
                doc.reference.delete()

            # Insert new assignments
            for batch, fac_id in batch_assignments.items():
                doc_ref = self.db.collection("batch_faculty").document()
                doc_ref.set({
                    "id": doc_ref.id,
                    "class_id": class_id,
                    "subject_id": subject_id,
                    "batch": batch,
                    "faculty_id": int(fac_id)
                })
        else:
            self._local_data["batch_faculty"] = [
                b for b in self._local_data.get("batch_faculty", [])
                if not (b["class_id"] == class_id and b["subject_id"] == subject_id)
            ]
            next_id = max([b.get("id", 0) for b in self._local_data.get("batch_faculty", [])], default=0) + 1
            for batch, fac_id in batch_assignments.items():
                self._local_data["batch_faculty"].append({
                    "id": next_id,
                    "class_id": class_id,
                    "subject_id": subject_id,
                    "batch": batch,
                    "faculty_id": int(fac_id)
                })
                next_id += 1
            self._save_local_data()

        # Also sync to faculty_allocations
        for batch, fac_id in batch_assignments.items():
            self.save_faculty_allocation(
                subject_id=subject_id,
                class_id=class_id,
                activity="Practical",
                batch=batch,
                faculty_id=int(fac_id),
                is_override=True
            )

        self.invalidate_cache()

    # =========================================================================
    # TIMETABLE GENERATION DATA (Fast In-Memory Preload)
    # =========================================================================
    def get_timetable_input_data(self):
        """
        Pre-loads all necessary timetable generation entities in memory,
        performing joins in-memory in < 1ms.
        """
        classes = [dict(c) for c in self.get_classes()]
        faculty = [dict(f) for f in self.get_faculty()]
        rooms = [dict(r) for r in self.get_rooms()]
        subjects = [dict(s) for s in self.get_subjects(fetch_faculty_names=True)]
        batch_faculty = [dict(b) for b in self.get_batch_faculty()]
        faculty_allocations = [dict(a) for a in self.get_faculty_allocations()]

        return {
            "classes": classes,
            "faculty": faculty,
            "rooms": rooms,
            "subjects": subjects,
            "batch_faculty": batch_faculty,
            "faculty_allocations": faculty_allocations
        }

    # =========================================================================
    # USERS & AUTHENTICATION
    # =========================================================================
    def _init_users(self):
        """Seeds default admin, teacher, and student accounts if none exist."""
        try:
            users = self.get_users()
            if not users:
                logger.info("No users found. Seeding default admin, teacher, and student accounts...")
                # Admin
                self.create_user(
                    username="admin",
                    password="admin123",
                    role="admin",
                    name="System Administrator"
                )
                # Sample Teacher (linked to faculty 1: Mrs. P. R. Chougule or first faculty)
                faculty_list = self.get_faculty()
                fac_id = faculty_list[0]["id"] if faculty_list else 1
                fac_name = faculty_list[0]["name"] if faculty_list else "Teacher Faculty"
                self.create_user(
                    username="teacher",
                    password="teacher123",
                    role="teacher",
                    name=fac_name,
                    faculty_id=fac_id
                )
                # Sample Student (linked to SY-A, batch A1)
                self.create_user(
                    username="student",
                    password="student123",
                    role="student",
                    name="SY-A Student",
                    class_name="SY-A",
                    batch="A1"
                )
        except Exception as e:
            logger.warning(f"Error seeding users: {e}")

    def get_users(self) -> List[Record]:
        cache_key = "users"
        if cache_key in self.cache:
            return self.cache[cache_key]

        tuple_keys = [
            "username", "role", "name", "faculty_id", "class_name", "batch",
            "department", "email", "phone", "academic_year", "semester",
            "status", "registered_at", "last_login", "last_logout"
        ]
        records = []
        if self.is_connected:
            docs = self.db.collection("users").stream()
            for doc in docs:
                d = doc.to_dict()
                records.append(Record(d, tuple_keys))
        else:
            for item in self._local_data.get("users", []):
                records.append(Record(dict(item), tuple_keys))

        self.cache[cache_key] = records
        return records

    def get_user_by_username(self, username: str) -> Optional[Record]:
        clean_user = str(username).strip().lower()
        users = self.get_users()
        # 1. Exact username match
        for u in users:
            if str(u.get("username", "")).strip().lower() == clean_user:
                return u
        # 2. Match by teacher name
        for u in users:
            if u.get("role") == "teacher" and str(u.get("name", "")).strip().lower() == clean_user:
                return u
        return None

    def get_user_by_email(self, email: str) -> Optional[Record]:
        clean_email = str(email).strip().lower()
        if not clean_email:
            return None
        for u in self.get_users():
            if str(u.get("email", "")).strip().lower() == clean_email:
                return u
        return None

    def get_pending_users(self) -> List[Record]:
        return [u for u in self.get_users() if u.get("status") == "pending"]

    def create_user(self, username: str, password: str, role: str, name: str,
                    faculty_id: Optional[int] = None, class_name: Optional[str] = None,
                    batch: Optional[str] = None, department: Optional[str] = None,
                    email: Optional[str] = None, phone: Optional[str] = None,
                    academic_year: Optional[str] = None, semester: Optional[str] = None,
                    status: str = "active"):
        username = str(username).strip().lower()
        password_hash = generate_password_hash(password)
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data = {
            "username": username,
            "password_hash": password_hash,
            "role": role.strip().lower(),
            "name": name.strip(),
            "faculty_id": int(faculty_id) if faculty_id else None,
            "class_name": class_name.strip() if class_name else None,
            "batch": batch.strip().upper() if batch else None,
            "department": str(department).strip() if department else None,
            "email": str(email).strip().lower() if email else None,
            "phone": str(phone).strip() if phone else None,
            "academic_year": str(academic_year).strip() if academic_year else None,
            "semester": str(semester).strip() if semester else None,
            "status": str(status).strip().lower(),
            "registered_at": now_str
        }

        if self.is_connected:
            self.db.collection("users").document(username).set(data)
        else:
            self._local_data.setdefault("users", [])
            self._local_data["users"] = [u for u in self._local_data["users"] if u.get("username") != username]
            self._local_data["users"].append(data)
            self._save_local_data()

        self.invalidate_cache()
        return data

    def update_user_status(self, username: str, new_status: str) -> bool:
        clean_user = str(username).strip().lower()
        status_val = str(new_status).strip().lower()
        if self.is_connected:
            try:
                self.db.collection("users").document(clean_user).set({"status": status_val}, merge=True)
            except Exception as e:
                logger.warning(f"Error updating user status in Firestore: {e}")
                return False
        else:
            for u in self._local_data.get("users", []):
                if u.get("username") == clean_user:
                    u["status"] = status_val
                    break
            self._save_local_data()
        self.invalidate_cache()
        return True

    def update_user_password(self, username: str, new_password: str) -> bool:
        clean_user = str(username).strip().lower()
        new_hash = generate_password_hash(new_password)
        if self.is_connected:
            try:
                self.db.collection("users").document(clean_user).set({
                    "password_hash": new_hash,
                    "password": new_password
                }, merge=True)
            except Exception as e:
                logger.warning(f"Error updating password in Firestore: {e}")
                return False
        else:
            for u in self._local_data.get("users", []):
                if u.get("username") == clean_user:
                    u["password_hash"] = new_hash
                    u["password"] = new_password
                    break
            self._save_local_data()
        self.invalidate_cache()
        return True

    def delete_user(self, username: str):
        username = str(username).strip().lower()
        if self.is_connected:
            self.db.collection("users").document(username).delete()
        else:
            self._local_data["users"] = [
                u for u in self._local_data.get("users", [])
                if u.get("username") != username
            ]
            self._save_local_data()

        self.invalidate_cache()

    def authenticate(self, username: str, password: str) -> Optional[Record]:
        user = self.get_user_by_username(username)
        if not user:
            return None
        pwd_hash = user.get("password_hash")
        if pwd_hash and check_password_hash(pwd_hash, password):
            return user
        if user.get("password") == password:
            return user
        return None

    # =========================================================================
    # LOGIN / LOGOUT AUDIT LOGS IN FIREBASE
    # =========================================================================
    def log_auth_event(self, username: Optional[str], name: Optional[str],
                       role: Optional[str], action: str,
                       ip_address: Optional[str] = None,
                       user_agent: Optional[str] = None):
        """
        Records a login or logout event in the 'auth_logs' collection in Firebase Firestore,
        and updates the user's online status and last login/logout timestamps.
        """
        clean_user = str(username or "unknown").strip().lower()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        log_data = {
            "username": clean_user,
            "name": str(name or clean_user).strip(),
            "role": str(role or "unknown").strip().lower(),
            "action": str(action).strip().upper(),  # 'LOGIN', 'LOGOUT', 'LOGIN_FAILED'
            "timestamp": now_str,
            "ip_address": str(ip_address or "127.0.0.1"),
            "user_agent": str(user_agent or "Unknown")[:120]  # truncate long user agents
        }

        if self.is_connected:
            try:
                # 1. Create audit log document in 'auth_logs' collection
                self.db.collection("auth_logs").document().set(log_data)

                # 2. Update user status in 'users' collection if valid user
                if clean_user != "unknown":
                    user_ref = self.db.collection("users").document(clean_user)
                    user_doc = user_ref.get()
                    if user_doc.exists:
                        update_payload = {}
                        if log_data["action"] == "LOGIN":
                            update_payload["last_login"] = now_str
                            update_payload["status"] = "online"
                        elif log_data["action"] == "LOGOUT":
                            update_payload["last_logout"] = now_str
                            update_payload["status"] = "offline"

                        if update_payload:
                            user_ref.set(update_payload, merge=True)
            except Exception as e:
                logger.warning(f"Failed to record auth log in Firebase: {e}")
        else:
            self._local_data.setdefault("auth_logs", []).append(log_data)
            # Update user in local data
            if clean_user != "unknown":
                for u in self._local_data.get("users", []):
                    if u.get("username") == clean_user:
                        if log_data["action"] == "LOGIN":
                            u["last_login"] = now_str
                            u["status"] = "online"
                        elif log_data["action"] == "LOGOUT":
                            u["last_logout"] = now_str
                            u["status"] = "offline"
                        break
            self._save_local_data()

    def get_auth_logs(self, limit: int = 50) -> List[Record]:
        """
        Retrieves recent login and logout audit logs from Firebase Firestore.
        """
        tuple_keys = ["username", "name", "role", "action", "timestamp", "ip_address", "user_agent"]
        logs = []

        if self.is_connected:
            try:
                query = self.db.collection("auth_logs").order_by(
                    "timestamp", direction="DESCENDING"
                ).limit(limit)
                docs = query.stream()
                for doc in docs:
                    d = doc.to_dict()
                    logs.append(Record(d, tuple_keys))
            except Exception as e:
                logger.warning(f"Error fetching auth logs from Firestore: {e}")
                # Fallback to streaming without order if index is pending
                docs = self.db.collection("auth_logs").limit(limit).stream()
                for doc in docs:
                    d = doc.to_dict()
                    logs.append(Record(d, tuple_keys))
                logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
        else:
            for item in self._local_data.get("auth_logs", []):
                logs.append(Record(dict(item), tuple_keys))
            logs.sort(key=lambda x: x.get("timestamp", ""), reverse=True)

        return logs[:limit]


    # =========================================================================
    # PERSONALIZED SCHEDULE VIEWS
    # =========================================================================
    def get_teacher_schedule(self, faculty_id: int, master_tt: Dict[str, Any]) -> List[List[List[Dict[str, Any]]]]:
        """
        Filters master timetable to return a 5x6 grid of events for a specific teacher.
        Grid cell: list of event dicts [{'class': str, 'text': str, 'type': str}]
        """
        import re
        faculty_id = int(faculty_id)
        faculty_map = {f["id"]: f["name"] for f in self.get_faculty()}
        target_name = faculty_map.get(faculty_id, "").strip()

        schedule = [[[] for _ in range(6)] for _ in range(5)]

        if not target_name or not master_tt:
            return schedule

        target_clean = re.sub(r'^(mr|mrs|ms|dr)\.?\s*', '', target_name, flags=re.IGNORECASE).strip().lower()

        def is_match(line_text: str) -> bool:
            lt = line_text.lower()
            return (
                f"({target_name.lower()})" in lt
                or f"({target_clean})" in lt
                or target_name.lower() in lt
                or (len(target_clean) > 3 and target_clean in lt)
            )

        for cname, days in master_tt.items():
            for day_idx in range(5):
                for p_idx in range(6):
                    cell = days[day_idx][p_idx]
                    if not cell:
                        continue

                    # Multi-line / batch slots (Practical or Tutorial)
                    if "<br>" in cell:
                        lines = cell.split("<br>")
                        for line in lines:
                            if is_match(line):
                                act_type = "Tutorial" if ("tut" in line.lower() or "tutorial" in line.lower()) else "Practical"
                                schedule[day_idx][p_idx].append({
                                    "class": cname,
                                    "text": line,
                                    "type": act_type
                                })
                    elif cell == "CONT":
                        if p_idx > 0 and any(e.get("class") == cname for e in schedule[day_idx][p_idx - 1]):
                            prev_entry = next((e for e in schedule[day_idx][p_idx - 1] if e.get("class") == cname), None)
                            schedule[day_idx][p_idx].append({
                                "class": cname,
                                "text": f"{prev_entry['text']} (Contd.)" if prev_entry else "Session (Continued)",
                                "type": prev_entry.get("type", "Practical") if prev_entry else "Practical"
                            })
                    else:
                        if is_match(cell):
                            act_type = "Tutorial" if ("tut" in cell.lower() or "tutorial" in cell.lower()) else "Theory"
                            schedule[day_idx][p_idx].append({
                                "class": cname,
                                "text": cell,
                                "type": act_type
                            })

        return schedule


    def get_student_schedule(self, class_name: str, batch: str, master_tt: Dict[str, Any]) -> List[List[str]]:
        """
        Filters master timetable for a specific class and batch.
        If a practical slot contains 4 batches, keeps ONLY the line for the student's batch.
        """
        class_name = class_name.strip()
        batch = batch.strip().upper()

        schedule = [["" for _ in range(6)] for _ in range(5)]
        class_table = master_tt.get(class_name)
        if not class_table:
            return schedule

        for day_idx in range(5):
            for p_idx in range(6):
                cell = class_table[day_idx][p_idx]
                if not cell:
                    continue

                if "<br>" in cell:
                    lines = cell.split("<br>")
                    batch_line = None
                    for line in lines:
                        if line.strip().endswith(f"- {batch}") or f"- {batch}" in line:
                            batch_line = line
                            break
                    schedule[day_idx][p_idx] = batch_line if batch_line else cell
                elif cell == "CONT":
                    prev_cell = schedule[day_idx][p_idx - 1] if p_idx > 0 else ""
                    if prev_cell and prev_cell != "Library / Self-Study":
                        schedule[day_idx][p_idx] = f"{prev_cell} (Contd.)"
                    else:
                        schedule[day_idx][p_idx] = "Practical (Continued)"
                else:
                    schedule[day_idx][p_idx] = cell

        return schedule

    # =========================================================================
    # TIMETABLE LIFECYCLE, MULTI-STAGE APPROVAL & PUBLISHING
    # =========================================================================

    def _init_timetable_storage(self):
        """Initializes draft, published, and history records if not present."""
        try:
            # 1. Initialize History if not exists
            if not os.path.exists(TIMETABLE_HISTORY_FILE):
                os.makedirs(os.path.dirname(TIMETABLE_HISTORY_FILE), exist_ok=True)
                initial_history = [{
                    "id": "1",
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "action": "PUBLISHED",
                    "version": 1,
                    "status": "Published",
                    "admin_username": "admin",
                    "admin_name": "System Administrator",
                    "description": "System baseline timetable initialized and published."
                }]
                with open(TIMETABLE_HISTORY_FILE, "w", encoding="utf-8") as f:
                    json.dump(initial_history, f, indent=2)

            # 2. Check if published and draft exist. If not, seed from master_timetable.json
            master_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database", "master_timetable.json")
            existing_data = None
            if os.path.exists(master_file):
                try:
                    with open(master_file, "r", encoding="utf-8") as f:
                        existing_data = json.load(f)
                except Exception as e:
                    logger.warning(f"Error reading master_timetable.json: {e}")

            if not existing_data:
                from generator import generate_timetable
                existing_data = generate_timetable(self)

            now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            if not os.path.exists(PUBLISHED_TIMETABLE_FILE):
                published_payload = {
                    "data": existing_data,
                    "status": "Published",
                    "version": 1,
                    "created_at": now_str,
                    "updated_at": now_str,
                    "published_at": now_str,
                    "published_by": "System Administrator (@admin)"
                }
                with open(PUBLISHED_TIMETABLE_FILE, "w", encoding="utf-8") as f:
                    json.dump(published_payload, f, indent=2)

            if not os.path.exists(DRAFT_TIMETABLE_FILE):
                draft_payload = {
                    "data": existing_data,
                    "status": "Published",
                    "version": 1,
                    "created_at": now_str,
                    "updated_at": now_str,
                    "updated_by": "System Administrator (@admin)",
                    "approved_at": now_str,
                    "approved_by": "System Administrator (@admin)",
                    "published_at": now_str,
                    "published_by": "System Administrator (@admin)"
                }
                with open(DRAFT_TIMETABLE_FILE, "w", encoding="utf-8") as f:
                    json.dump(draft_payload, f, indent=2)

        except Exception as e:
            logger.warning(f"Error in _init_timetable_storage: {e}")

    def get_working_timetable(self) -> Dict[str, Any]:
        """
        Retrieves the working/draft timetable document.
        Contains 'data', 'status' (Draft/Pending Approval/Approved/Published),
        'version', timestamps, and audit info.
        """
        if self._cached_draft_timetable is not None:
            return self._cached_draft_timetable

        # Try Firestore first if connected
        if self.is_connected and self.db:
            try:
                doc = self.db.collection("timetables").document("draft").get()
                if doc.exists:
                    d = doc.to_dict()
                    if d:
                        if "json_data" in d:
                            d["data"] = json.loads(d["json_data"])
                        self._cached_draft_timetable = d
                        return d
            except Exception as e:
                logger.warning(f"Could not load draft timetable from Firestore: {e}")

        # Fallback to local file
        if os.path.exists(DRAFT_TIMETABLE_FILE):
            try:
                with open(DRAFT_TIMETABLE_FILE, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    self._cached_draft_timetable = d
                    return d
            except Exception as e:
                logger.warning(f"Error reading draft_timetable.json: {e}")

        # If not found, initialize
        self._init_timetable_storage()
        if os.path.exists(DRAFT_TIMETABLE_FILE):
            with open(DRAFT_TIMETABLE_FILE, "r", encoding="utf-8") as f:
                d = json.load(f)
                self._cached_draft_timetable = d
                return d

        return {"data": {}, "status": "Draft", "version": 1}

    def get_published_timetable(self) -> Optional[Dict[str, Any]]:
        """
        Retrieves the active published timetable document visible to teachers and students.
        Returns None or empty dict if no timetable has been published yet.
        """
        if self._cached_published_timetable is not None:
            return self._cached_published_timetable

        if self.is_connected and self.db:
            try:
                doc = self.db.collection("timetables").document("published").get()
                if doc.exists:
                    d = doc.to_dict()
                    if d:
                        if "json_data" in d:
                            d["data"] = json.loads(d["json_data"])
                        self._cached_published_timetable = d
                        return d
            except Exception as e:
                logger.warning(f"Could not load published timetable from Firestore: {e}")

        if os.path.exists(PUBLISHED_TIMETABLE_FILE):
            try:
                with open(PUBLISHED_TIMETABLE_FILE, "r", encoding="utf-8") as f:
                    d = json.load(f)
                    self._cached_published_timetable = d
                    return d
            except Exception as e:
                logger.warning(f"Error reading published_timetable.json: {e}")

        return None

    def get_published_timetable_data(self) -> Dict[str, Any]:
        """Returns just the 'data' dictionary of the published timetable."""
        pub = self.get_published_timetable()
        if pub and isinstance(pub, dict) and "data" in pub:
            return pub["data"]
        return {}

    def save_working_timetable(self, working_tt: Dict[str, Any]) -> None:
        """Saves working timetable to cache, local file, and Firestore."""
        self._cached_draft_timetable = working_tt
        try:
            os.makedirs(os.path.dirname(DRAFT_TIMETABLE_FILE), exist_ok=True)
            with open(DRAFT_TIMETABLE_FILE, "w", encoding="utf-8") as f:
                json.dump(working_tt, f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save draft_timetable.json: {e}")

        if self.is_connected and self.db:
            try:
                from firebase_admin import firestore
                data_to_store = dict(working_tt)
                if "data" in data_to_store:
                    json_str = json.dumps(data_to_store.pop("data"))
                    data_to_store["json_data"] = json_str
                data_to_store["updated_at_fs"] = firestore.SERVER_TIMESTAMP
                self.db.collection("timetables").document("draft").set(data_to_store)
            except Exception as e:
                logger.warning(f"Could not save draft timetable to Firestore: {e}")

    def save_published_timetable(self, published_tt: Dict[str, Any]) -> None:
        """Saves published timetable snapshot to cache, local file, and Firestore."""
        self._cached_published_timetable = published_tt
        self._cached_master_timetable = published_tt.get("data")
        try:
            os.makedirs(os.path.dirname(PUBLISHED_TIMETABLE_FILE), exist_ok=True)
            with open(PUBLISHED_TIMETABLE_FILE, "w", encoding="utf-8") as f:
                json.dump(published_tt, f, indent=2)

            # Keep legacy master_timetable.json in sync
            master_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), "database", "master_timetable.json")
            with open(master_file, "w", encoding="utf-8") as f:
                json.dump(published_tt.get("data", {}), f, indent=2)
        except Exception as e:
            logger.warning(f"Could not save published_timetable.json: {e}")

        if self.is_connected and self.db:
            try:
                from firebase_admin import firestore
                data_to_store = dict(published_tt)
                if "data" in data_to_store:
                    json_str = json.dumps(data_to_store.pop("data"))
                    data_to_store["json_data"] = json_str
                data_to_store["updated_at_fs"] = firestore.SERVER_TIMESTAMP
                self.db.collection("timetables").document("published").set(data_to_store)
                # Keep master document in sync
                self.db.collection("timetables").document("master").set({
                    "json_data": data_to_store.get("json_data", "{}"),
                    "updated_at": firestore.SERVER_TIMESTAMP
                })
            except Exception as e:
                logger.warning(f"Could not save published timetable to Firestore: {e}")

    def generate_draft_timetable(self, admin_username: str = "admin", admin_name: str = "System Administrator") -> Dict[str, Any]:
        """
        Generates a fresh clash-free timetable as a Draft.
        Increments version and sets status to 'Draft'.
        Does NOT alter published schedule.
        """
        from generator import generate_timetable
        new_data = generate_timetable(self)

        current = self.get_working_timetable()
        curr_ver = current.get("version", 1)
        # If previous status was Published, bump version number
        new_version = curr_ver + 1 if current.get("status") == "Published" else curr_ver
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        draft_payload = {
            "data": new_data,
            "status": "Draft",
            "version": new_version,
            "created_at": now_str,
            "updated_at": now_str,
            "updated_by": f"{admin_name} (@{admin_username})",
            "approved_by": None,
            "approved_at": None,
            "published_by": None,
            "published_at": None
        }

        self.save_working_timetable(draft_payload)
        self.log_timetable_event(
            action="GENERATED",
            version=new_version,
            status="Draft",
            admin_username=admin_username,
            admin_name=admin_name,
            description=f"Generated new clash-free draft timetable (Version {new_version})."
        )
        return draft_payload

    def update_timetable_status(self, new_status: str, admin_username: str = "admin", admin_name: str = "System Administrator", notes: str = "") -> Dict[str, Any]:
        """
        Transitions timetable through its lifecycle:
        Draft -> Pending Approval -> Approved -> Published (or back to Draft).
        """
        allowed_statuses = ["Draft", "Pending Approval", "Approved", "Published"]
        if new_status not in allowed_statuses:
            raise ValueError(f"Invalid status '{new_status}'. Must be one of {allowed_statuses}")

        working = self.get_working_timetable()
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        version = working.get("version", 1)

        working["status"] = new_status
        working["updated_at"] = now_str
        working["updated_by"] = f"{admin_name} (@{admin_username})"

        action = "STATUS_CHANGE"
        description = f"Status updated to '{new_status}'."

        if new_status == "Pending Approval":
            action = "SUBMITTED"
            description = f"Timetable v{version} submitted for admin approval review."
        elif new_status == "Approved":
            working["approved_at"] = now_str
            working["approved_by"] = f"{admin_name} (@{admin_username})"
            action = "APPROVED"
            description = f"Timetable v{version} reviewed and approved by {admin_name}."
        elif new_status == "Published":
            working["published_at"] = now_str
            working["published_by"] = f"{admin_name} (@{admin_username})"
            action = "PUBLISHED"
            description = f"Timetable v{version} published to all student and teacher portals."

            # Update live published snapshot
            published_payload = {
                "data": working["data"],
                "status": "Published",
                "version": version,
                "created_at": working.get("created_at", now_str),
                "updated_at": now_str,
                "published_at": now_str,
                "published_by": f"{admin_name} (@{admin_username})"
            }
            self.save_published_timetable(published_payload)
        elif new_status == "Draft":
            action = "REVERTED"
            description = f"Timetable v{version} moved back to Draft for revisions."

        if notes:
            description += f" Note: {notes}"

        self.save_working_timetable(working)
        self.log_timetable_event(
            action=action,
            version=version,
            status=new_status,
            admin_username=admin_username,
            admin_name=admin_name,
            description=description
        )
        return working

    def edit_timetable_slot(self, class_name: str, day_idx: int, period_idx: int, new_value: str, admin_username: str = "admin", admin_name: str = "System Administrator") -> Dict[str, Any]:
        """
        Manually modifies a specific slot in the working timetable.
        Resets status to 'Draft' so modifications require approval and publishing.
        """
        working = self.get_working_timetable()
        data = working.get("data", {})
        if class_name not in data:
            raise KeyError(f"Class '{class_name}' not found in timetable.")

        day_names = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday"]
        d_name = day_names[day_idx] if 0 <= day_idx < len(day_names) else f"Day {day_idx}"
        p_num = period_idx + 1

        old_val = data[class_name][day_idx][period_idx]
        data[class_name][day_idx][period_idx] = new_value.strip()

        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        working["data"] = data
        working["status"] = "Draft"
        working["updated_at"] = now_str
        working["updated_by"] = f"{admin_name} (@{admin_username})"

        self.save_working_timetable(working)
        self.log_timetable_event(
            action="EDITED_SLOT",
            version=working.get("version", 1),
            status="Draft",
            admin_username=admin_username,
            admin_name=admin_name,
            description=f"Edited {class_name} ({d_name} Period {p_num}) from '{old_val}' to '{new_value}'."
        )
        return working

    def get_room_schedule(self, room_name: str, timetable_data: Dict[str, Any]) -> List[List[List[Dict[str, Any]]]]:
        """
        Computes 5-day x 6-period allocation matrix for a specific Classroom or Lab.
        Grid cell: list of event dicts [{'class': str, 'batch': str, 'text': str, 'type': str}]
        """
        room_name_clean = room_name.strip()
        room_key = f"[{room_name_clean.lower()}]"

        schedule = [[[] for _ in range(6)] for _ in range(5)]
        if not timetable_data or not room_name_clean:
            return schedule

        for cname, days in timetable_data.items():
            for day_idx in range(5):
                for p_idx in range(6):
                    cell = days[day_idx][p_idx]
                    if not cell:
                        continue

                    # Practical block with multiple batch lines
                    if "<br>" in cell:
                        lines = cell.split("<br>")
                        for line in lines:
                            if room_key in line.lower() or f"[{room_name_clean.lower()}" in line.lower():
                                parts = line.split(" - ")
                                batch_part = parts[-1].strip() if len(parts) > 1 else ""
                                schedule[day_idx][p_idx].append({
                                    "class": cname,
                                    "batch": batch_part,
                                    "text": line,
                                    "type": "Practical"
                                })
                    elif cell == "CONT":
                        if p_idx > 0:
                            for prev_ev in schedule[day_idx][p_idx - 1]:
                                if prev_ev.get("class") == cname:
                                    schedule[day_idx][p_idx].append({
                                        "class": cname,
                                        "batch": prev_ev.get("batch", ""),
                                        "text": f"{prev_ev.get('text', '')} (Contd.)",
                                        "type": "Practical"
                                    })
                    else:
                        if room_key in cell.lower() or f"[{room_name_clean.lower()}" in cell.lower():
                            schedule[day_idx][p_idx].append({
                                "class": cname,
                                "batch": "",
                                "text": cell,
                                "type": "Theory"
                            })

        return schedule

    def get_timetable_history(self, limit: int = 50) -> List[Dict[str, Any]]:
        """Retrieves timetable version change and audit history."""
        # Try Firestore
        if self.is_connected and self.db:
            try:
                docs = (
                    self.db.collection("timetable_history")
                    .order_by("timestamp", direction="DESCENDING")
                    .limit(limit)
                    .stream()
                )
                history = [d.to_dict() for d in docs]
                if history:
                    return history
            except Exception as e:
                logger.warning(f"Could not fetch history from Firestore: {e}")

        # Fallback to local file
        if os.path.exists(TIMETABLE_HISTORY_FILE):
            try:
                with open(TIMETABLE_HISTORY_FILE, "r", encoding="utf-8") as f:
                    history = json.load(f)
                    history.sort(key=lambda x: x.get("timestamp", ""), reverse=True)
                    return history[:limit]
            except Exception as e:
                logger.warning(f"Error reading timetable_history.json: {e}")

        return []

    def log_timetable_event(self, action: str, version: int, status: str, admin_username: str, admin_name: str, description: str):
        """Records an audit event in local JSON and Firestore."""
        import uuid
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        record = {
            "id": str(uuid.uuid4())[:8],
            "timestamp": now_str,
            "action": action,
            "version": version,
            "status": status,
            "admin_username": admin_username,
            "admin_name": admin_name,
            "description": description
        }

        # Save to local file
        try:
            os.makedirs(os.path.dirname(TIMETABLE_HISTORY_FILE), exist_ok=True)
            history = []
            if os.path.exists(TIMETABLE_HISTORY_FILE):
                with open(TIMETABLE_HISTORY_FILE, "r", encoding="utf-8") as f:
                    history = json.load(f)
            history.insert(0, record)
            with open(TIMETABLE_HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(history[:200], f, indent=2)
        except Exception as e:
            logger.warning(f"Could not append to timetable_history.json: {e}")

        # Save to Firestore
        if self.is_connected and self.db:
            try:
                from firebase_admin import firestore
                record["fs_timestamp"] = firestore.SERVER_TIMESTAMP
                self.db.collection("timetable_history").document(record["id"]).set(record)
            except Exception as e:
                logger.warning(f"Could not log timetable event to Firestore: {e}")

    def get_master_timetable(self, force_regenerate: bool = False) -> Dict[str, Any]:
        """Backward-compatible method returning published timetable data, or generating if empty."""
        if force_regenerate:
            draft = self.generate_draft_timetable()
            return draft.get("data", {})

        pub_data = self.get_published_timetable_data()
        if pub_data:
            return pub_data

        working = self.get_working_timetable()
        return working.get("data", {})

    def save_master_timetable(self, timetable: Dict[str, Any]) -> None:
        """Backward-compatible method saving to working timetable."""
        working = self.get_working_timetable()
        working["data"] = timetable
        self.save_working_timetable(working)

# Global singleton instance
service = FirebaseService()
db = service

def get_db():
    return service

