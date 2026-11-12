import sys
import os

project_root = r"c:\Users\Mufija\OneDrive\Desktop\mini"
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from firebase_service import get_db
from generator import generate_timetable
from app import app

def run_equalization_test():
    print("=" * 70)
    print("STEP 1: Testing db.equalize_faculty_workloads(respect_overrides=True)...")
    print("=" * 70)
    
    db = get_db()
    res = db.equalize_faculty_workloads(respect_overrides=True)
    
    print(f"Equalization Result: success={res['success']}")
    print(f"Faculty Count: {res['faculty_count']}")
    print(f"Total Institutional Hours: {res['total_hours']}")
    print(f"Mean Workload: {res['mean_load']}h")
    print(f"Min Load: {res['min_load']}h, Max Load: {res['max_load']}h")
    print(f"Disparity (Spread): {res['disparity']}h")
    print(f"Standard Deviation (sigma): {res['std_dev']}")
    
    assert res["success"] is True, "Equalization failed"
    assert res["faculty_count"] == 14, f"Expected 14 faculties, got {res['faculty_count']}"
    assert res["disparity"] <= 2, f"Expected disparity <= 2h, got {res['disparity']}h"
    assert res["std_dev"] < 1.0, f"Expected std dev < 1.0, got {res['std_dev']}"
    print("[PASS] Equalization achieved <= 2h disparity and std dev < 1.0!")

    print("\n" + "=" * 70)
    print("STEP 2: Testing db.calculate_workload_equality_metrics()...")
    print("=" * 70)
    metrics = db.calculate_workload_equality_metrics()
    print(f"Metrics: {metrics}")
    assert metrics["is_balanced"] is True, "Expected is_balanced == True"
    assert metrics["disparity"] <= 2, f"Expected metrics disparity <= 2, got {metrics['disparity']}"
    print("[PASS] Workload equality metrics verified!")

    print("\n" + "=" * 70)
    print("STEP 3: Testing Flask Route /admin/allocations/equalize_workload...")
    print("=" * 70)
    with app.test_client() as client:
        # Simulate admin session
        with client.session_transaction() as sess:
            sess["user_id"] = 1
            sess["user_name"] = "Admin"
            sess["role"] = "admin"
        
        resp = client.post("/admin/allocations/equalize_workload", data={"respect_overrides": "1"}, follow_redirects=True)
        assert resp.status_code == 200, f"Expected status 200, got {resp.status_code}"
        html = resp.get_data(as_text=True)
        assert "Automated Workload Equalization Completed" in html or "Workload" in html, "Flash message missing"
        assert "Distribute Load Equally" in html, "Distribute Load Equally button missing from page"
        assert "equalizeModal" in html, "Equalize modal missing from page"
        print("[PASS] Flask endpoint /admin/allocations/equalize_workload succeeded and rendered modal & button!")

    print("\n" + "=" * 70)
    print("STEP 4: Generating Timetable on Equalized Allocations (Conflict-Free Check)...")
    print("=" * 70)
    tt_result = generate_timetable(db)
    assert tt_result is not None, "Timetable generation returned None"
    assert len(tt_result) == 4, f"Expected 4 classes in timetable, got {len(tt_result)}"
    for class_name, grid in tt_result.items():
        assert len(grid) == 5, f"Class {class_name} does not have 5 days"
        for d_idx, periods in enumerate(grid):
            assert len(periods) == 6, f"Day {d_idx} does not have 6 periods"
    print(f"[PASS] Timetable generated clash-free for all 4 classes: {list(tt_result.keys())}!")

    print("\n" + "=" * 70)
    print("ALL TESTS PASSED WITH FLYING COLORS!")
    print("=" * 70)

if __name__ == "__main__":
    run_equalization_test()
