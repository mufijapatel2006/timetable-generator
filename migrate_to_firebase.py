"""
Safe Data Migration Script: MySQL Backup -> Firebase Firestore
Transfers all classes, faculty, rooms, subjects, and batch assignments from
the verified database/backup_data.json to Firebase Cloud Firestore collections.
"""

import os
import sys
import json
import logging
from firebase_service import CREDENTIAL_FILES, BACKUP_DATA_FILE

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
logger = logging.getLogger("FirebaseMigration")

def run_migration():
    cred_path = None
    for path in [
        os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"),
        os.environ.get("FIREBASE_CREDENTIALS"),
        *[os.path.join(os.path.dirname(os.path.abspath(__file__)), f) for f in CREDENTIAL_FILES]
    ]:
        if path and os.path.isfile(path):
            cred_path = path
            break

    if not cred_path:
        logger.error(
            "ERROR: No Firebase service account key found!\n"
            "Please place your 'serviceAccountKey.json' file in this directory:\n"
            f"  {os.path.dirname(os.path.abspath(__file__))}\n"
            "You can download this key from the Firebase Console -> Project Settings -> Service Accounts."
        )
        return False

    if not os.path.exists(BACKUP_DATA_FILE):
        logger.error(f"ERROR: Backup file not found at: {BACKUP_DATA_FILE}")
        return False

    with open(BACKUP_DATA_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    logger.info(f"Loaded source data from {BACKUP_DATA_FILE}:")
    for table, records in data.items():
        logger.info(f"  - {table}: {len(records)} records")

    import firebase_admin
    from firebase_admin import credentials, firestore

    if not firebase_admin._apps:
        cred = credentials.Certificate(cred_path)
        firebase_admin.initialize_app(cred)

    db = firestore.client()
    logger.info("Connected to Firebase Cloud Firestore successfully.")

    # Faculty name lookup map for denormalization
    faculty_map = {f["id"]: f["name"] for f in data.get("faculty", [])}

    # 1. Migrate Classes
    logger.info("Migrating 'classes'...")
    batch = db.batch()
    batch_count = 0
    for cls in data.get("classes", []):
        doc_ref = db.collection("classes").document(str(cls["id"]))
        batch.set(doc_ref, {
            "id": int(cls["id"]),
            "name": str(cls["name"]).strip()
        })
        batch_count += 1
        if batch_count >= 400:
            batch.commit()
            batch = db.batch()
            batch_count = 0
    if batch_count > 0:
        batch.commit()
    logger.info(f"Migrated {len(data.get('classes', []))} classes.")

    # 2. Migrate Faculty
    logger.info("Migrating 'faculty'...")
    batch = db.batch()
    batch_count = 0
    for fac in data.get("faculty", []):
        doc_ref = db.collection("faculty").document(str(fac["id"]))
        batch.set(doc_ref, {
            "id": int(fac["id"]),
            "name": str(fac["name"]).strip()
        })
        batch_count += 1
        if batch_count >= 400:
            batch.commit()
            batch = db.batch()
            batch_count = 0
    if batch_count > 0:
        batch.commit()
    logger.info(f"Migrated {len(data.get('faculty', []))} faculty members.")

    # 3. Migrate Rooms
    logger.info("Migrating 'rooms'...")
    batch = db.batch()
    batch_count = 0
    for room in data.get("rooms", []):
        doc_ref = db.collection("rooms").document(str(room["id"]))
        batch.set(doc_ref, {
            "id": int(room["id"]),
            "name": str(room["name"]).strip(),
            "type": str(room["type"]).strip()
        })
        batch_count += 1
        if batch_count >= 400:
            batch.commit()
            batch = db.batch()
            batch_count = 0
    if batch_count > 0:
        batch.commit()
    logger.info(f"Migrated {len(data.get('rooms', []))} rooms.")

    # 4. Migrate Subjects
    logger.info("Migrating 'subjects'...")
    batch = db.batch()
    batch_count = 0
    for sub in data.get("subjects", []):
        doc_ref = db.collection("subjects").document(str(sub["id"]))
        batch.set(doc_ref, {
            "id": int(sub["id"]),
            "name": str(sub["name"]).strip(),
            "type": str(sub["type"]).strip(),
            "hours": int(sub["hours"]),
            "class_id": int(sub["class_id"]) if sub.get("class_id") is not None else None,
            "faculty_id": int(sub["faculty_id"]) if sub.get("faculty_id") is not None else None,
            "faculty_name": faculty_map.get(sub.get("faculty_id"), "")
        })
        batch_count += 1
        if batch_count >= 400:
            batch.commit()
            batch = db.batch()
            batch_count = 0
    if batch_count > 0:
        batch.commit()
    logger.info(f"Migrated {len(data.get('subjects', []))} subjects.")

    # 5. Migrate Batch Faculty
    logger.info("Migrating 'batch_faculty'...")
    batch = db.batch()
    batch_count = 0
    for bf in data.get("batch_faculty", []):
        doc_ref = db.collection("batch_faculty").document(str(bf["id"]))
        batch.set(doc_ref, {
            "id": int(bf["id"]),
            "class_id": int(bf["class_id"]),
            "subject_id": int(bf["subject_id"]),
            "batch": str(bf["batch"]).strip(),
            "faculty_id": int(bf["faculty_id"])
        })
        batch_count += 1
        if batch_count >= 400:
            batch.commit()
            batch = db.batch()
            batch_count = 0
    if batch_count > 0:
        batch.commit()
    logger.info(f"Migrated {len(data.get('batch_faculty', []))} batch_faculty assignments.")

    # Verification
    logger.info("\n--- VERIFYING FIRESTORE COUNTS ---")
    collections = ["classes", "faculty", "rooms", "subjects", "batch_faculty"]
    all_matched = True
    for col in collections:
        firestore_count = len(list(db.collection(col).stream()))
        source_count = len(data.get(col, []))
        logger.info(f"Collection '{col}': Firestore has {firestore_count} docs | Source had {source_count} docs")
        if firestore_count != source_count:
            all_matched = False
            logger.warning(f"  Count discrepancy detected in '{col}'!")

    if all_matched:
        logger.info("\nSUCCESS: All data successfully transferred and verified in Firebase Firestore with zero loss!")
    else:
        logger.warning("\nMigration finished with count warnings. Please review the counts above.")

    return all_matched

if __name__ == "__main__":
    success = run_migration()
    sys.exit(0 if success else 1)
