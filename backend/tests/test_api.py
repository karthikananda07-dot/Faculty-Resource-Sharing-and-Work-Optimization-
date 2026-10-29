"""Basic tests for the Dept Project API.
Run from the backend folder:   python -m pytest
"""
import pytest

DATES = {"Mon": "2026-10-26", "Tue": "2026-10-27", "Wed": "2026-10-28",
         "Thu": "2026-10-29", "Fri": "2026-10-30", "Sat": "2026-10-31"}


def mark_absent(client):
    """Mark some teacher who has classes as absent; return (teacher id, date, affected classes)."""
    for t in client.get("/faculty").json():
        rows = client.get("/timetable", params={"faculty_id": t["id"]}).json()
        if rows:
            date = DATES[rows[0]["day"]]
            res = client.post("/absences", json={"faculty_id": t["id"], "date": date, "reason": "test"})
            assert res.status_code == 200
            return t["id"], date, res.json()["affected_classes"]
    pytest.fail("the seed data has no teacher with a class")


def test_faculty_and_periods_are_loaded(client):
    assert len(client.get("/faculty").json()) > 0
    periods = client.get("/periods").json()
    assert len(periods) > 0 and periods[0]["period"] == 1


def test_timetable_day_filter(client):
    rows = client.get("/timetable", params={"day": "Mon"}).json()
    assert rows and all(r["day"] == "Mon" for r in rows)


def test_free_periods_have_no_teacher(client):
    rows = client.get("/timetable").json()
    assert all(r["faculty_id"] is None for r in rows if r["slot_type"] == "free")


def test_workload_adds_up(client):
    for w in client.get("/workload").json():
        assert w["remaining_hours"] == w["max_hours"] - w["weekly_hours"]


def test_absence_lists_affected_classes_and_substitutes(client):
    fid, date, affected = mark_absent(client)
    assert affected
    for slot in affected:
        assert slot["faculty_id"] == fid
        assert fid not in [s["id"] for s in slot["available_substitutes"]]


def test_absence_rejects_bad_date(client):
    res = client.post("/absences", json={"faculty_id": 1, "date": "27-10-2026"})
    assert res.status_code == 400


def test_absence_unknown_teacher(client):
    res = client.post("/absences", json={"faculty_id": 99999, "date": "2026-10-27"})
    assert res.status_code == 404


def test_exchange_request_and_accept(client):
    fid, date, affected = mark_absent(client)
    slot = next(s for s in affected if s["available_substitutes"])
    body = {"date": date, "period": slot["period"], "class_name": slot["class_name"],
            "from_faculty": fid, "to_faculty": slot["available_substitutes"][0]["id"]}
    res = client.post("/exchanges", json=body)
    assert res.status_code == 200 and res.json()["status"] == "pending"
    eid = res.json()["exchange_id"]
    accepted = client.post(f"/exchanges/{eid}/respond", json={"accept": True})
    assert accepted.json()["status"] == "accepted"
    assert client.post(f"/exchanges/{eid}/respond", json={"accept": False}).status_code == 409


def test_exchange_rejects_teacher_who_is_busy(client):
    rows = [r for r in client.get("/timetable").json() if r["faculty_id"] is not None]
    pair = next(((a, b) for a in rows for b in rows
                 if a["day"] == b["day"] and a["period"] == b["period"]
                 and a["faculty_id"] != b["faculty_id"]), None)
    if pair is None:
        pytest.skip("no two teachers share a period in the seed data")
    a, b = pair
    body = {"date": DATES[a["day"]], "period": a["period"], "class_name": a["class_name"],
            "from_faculty": a["faculty_id"], "to_faculty": b["faculty_id"]}
    assert client.post("/exchanges", json=body).status_code == 409


def test_timetable_blocks_double_booking(client):
    row = next(r for r in client.get("/timetable").json() if r["faculty_id"] is not None)
    clash = {"day": row["day"], "period": row["period"],
             "class_name": "TEST-X", "faculty_id": row["faculty_id"]}
    assert client.post("/timetable", json=clash).status_code == 409


def test_timetable_add_edit_delete(client):
    fid = client.get("/faculty").json()[0]["id"]
    slot = {"day": "Sat", "period": 9, "class_name": "TEST-X", "subject": "Test", "faculty_id": fid}
    created = client.post("/timetable", json=slot)
    assert created.status_code == 200
    sid = created.json()["id"]
    assert client.put(f"/timetable/{sid}", json={**slot, "subject": "Changed"}).status_code == 200
    assert client.delete(f"/timetable/{sid}").status_code == 200
    assert client.delete(f"/timetable/{sid}").status_code == 404


def test_optimizer_needs_an_absence_first(client):
    pytest.importorskip("ortools")
    res = client.post("/optimize-substitutes", json={"faculty_id": 1, "date": "2026-10-27"})
    assert res.status_code == 404


def test_optimizer_returns_one_result_per_affected_class(client):
    pytest.importorskip("ortools")
    fid, date, affected = mark_absent(client)
    res = client.post("/optimize-substitutes", json={"faculty_id": fid, "date": date})
    assert res.status_code == 200
    recs = res.json()["recommendations"]
    assert len(recs) == len(affected)
    assert all(r["status"] in ("recommended", "uncovered") for r in recs)
