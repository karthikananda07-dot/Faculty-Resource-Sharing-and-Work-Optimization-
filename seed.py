"""Fills dept.db with sample faculty + a weekly timetable (no teacher double-booked).
Run:  python seed.py
Replace FACULTY / CLASSES with your real department data."""
import random
from main import db, init_db

random.seed(42)
init_db()

FACULTY = [
    ("Dr. Anita Rao", "anita.rao@college.edu", "Mathematics"),
    ("Prof. Suresh Kumar", "suresh.kumar@college.edu", "Data Structures"),
    ("Dr. Meena Iyer", "meena.iyer@college.edu", "DBMS"),
    ("Prof. Rahul Verma", "rahul.verma@college.edu", "Operating Systems"),
    ("Dr. Kavya Nair", "kavya.nair@college.edu", "Computer Networks"),
    ("Prof. Arjun Reddy", "arjun.reddy@college.edu", "Java Programming"),
    ("Dr. Priya Sharma", "priya.sharma@college.edu", "Software Engineering"),
    ("Prof. Imran Khan", "imran.khan@college.edu", "Python Programming"),
]
CLASSES = ["CSE-A", "CSE-B", "CSE-C"]
DAYS = ["Mon", "Tue", "Wed", "Thu", "Fri"]
PERIODS = range(1, 7)

with db() as c:
    c.executescript("DELETE FROM timetable; DELETE FROM faculty; "
                    "DELETE FROM absences; DELETE FROM exchanges; DELETE FROM updates; DELETE FROM assignments;")
    ids = []
    for name, email, subject in FACULTY:
        cur = c.execute("INSERT INTO faculty(name,email,subject,max_hours) VALUES(?,?,?,?)",
                        (name, email, subject, 18))
        ids.append((cur.lastrowid, subject))

    for day in DAYS:
        for p in PERIODS:
            # pick a different teacher for each class this period
            for cls, (fid, subject) in zip(CLASSES, random.sample(ids, len(CLASSES))):
                room = f"R{101 + CLASSES.index(cls)}"
                c.execute("""INSERT INTO timetable(day,period,class_name,subject,room,faculty_id)
                             VALUES(?,?,?,?,?,?)""", (day, p, cls, subject, room, fid))

print("Seeded:", len(FACULTY), "faculty,", len(DAYS) * len(PERIODS) * len(CLASSES), "timetable slots")
