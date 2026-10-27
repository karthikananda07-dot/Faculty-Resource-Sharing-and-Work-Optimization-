"""Loads the real timetable for Semester III, Section D (2026-27 ODD SEM, w.e.f. 07/09/2026).
Run:  python seed.py
WARNING: wipes and recreates all tables - use only on a fresh or test database.
To add more sections/semesters later, add more teachers + another SCHEDULE block, or use
the POST /timetable and POST /faculty endpoints from the frontend."""
from main import db, init_db

with db() as c:
    c.executescript("""
        DROP TABLE IF EXISTS timetable;   DROP TABLE IF EXISTS faculty;
        DROP TABLE IF EXISTS absences;    DROP TABLE IF EXISTS exchanges;
        DROP TABLE IF EXISTS assignments; DROP TABLE IF EXISTS updates;
        DROP TABLE IF EXISTS periods;""")
init_db()

CLASS_NAME, ROOM = "III-D", "522"   # class teacher: Prof. Indra S

# (name, abbreviation) - emails and max hours are not in the timetable, fill them in later
FACULTY = [
    ("Prof. Anushree P", "ASP"), ("Prof. K. Indumathi", "KI"), ("Dr. J. Prakash", "JP"),
    ("Prof. Yashaswini R", "YR"), ("Prof. Lakshmi Prasanna T", "LPT"), ("Prof. Indra S", "IS"),
    ("Prof. Gomathi M", "GM"), ("Prof. Archana H", "AH"),
]
DEFAULT_MAX_HOURS = 18  # placeholder - replace with the real limit

# Period timings (tea break 10:20-10:40 and lunch 12:30-13:15 are not periods)
PERIODS = [(1, "08:30", "09:25"), (2, "09:25", "10:20"), (3, "10:40", "11:35"),
           (4, "11:35", "12:30"), (5, "13:15", "14:10"), (6, "14:10", "15:05"),
           (7, "15:05", "16:00")]

# key: (subject code, name, teacher abbreviation, type). Type "free" = no teacher is busy.
SUBJECTS = {
    "MCS301":    ("B25MCS301", "Probability and Statistics", "ASP", "class"),
    "CS302":     ("B25CS302", "Data Structures and its Applications", "KI", "class"),
    "CS303":     ("B25CS303", "Digital Design and Computer Organization", "JP", "class"),
    "CS304":     ("B25CS304", "Operating Systems", "LPT", "class"),
    "CS305":     ("B25CS305", "C++ Programming", "IS", "class"),
    "DSA_LAB":   ("B25CSL306", "Data Structures and its Applications Lab", "KI", "lab"),
    "CPP_LAB":   ("B25CSL307", "C++ Programming Lab", "IS", "lab"),   # printed as B25CS307 in the grid
    "DDCO_LAB":  ("B25CS303", "Digital Design and Computer Organization Lab", "YR", "lab"),
    "SKL300":    ("B25SKL300", "Skill Laboratory", "AH", "lab"),
    "CSP308":    ("B25CSP308", "Community / Societal Project", "IS", "class"),
    "MAD309":    ("B25MAD309", "Additional Mathematics - I", "GM", "class"),
    "NCK310":    ("B25NCK310", "NSS / NCC / Physical Education / Yoga / Music", "IS", "class"),  # printed as B25XXX310 - please confirm
    "MENTORING": (None, "Mentoring", None, "free"),
    "LIBRARY":   (None, "Library", None, "free"),
    "TUTORIAL":  (None, "Tutorial", None, "free"),
    "AICTE":     (None, "AICTE Activity Points", None, "free"),
}


def one(key):
    return [(key, None)]


# day -> list of (first period, last period, [(subject key, batch), ...])
# Two entries in one block = the class is split into batches D1/D2 running at the same time.
SCHEDULE = {
    "Mon": [(1, 1, one("CS305")), (2, 2, one("MCS301")),
            (3, 4, [("SKL300", "D2"), ("DDCO_LAB", "D1")]),
            (5, 5, one("CS302")), (6, 6, one("MENTORING")), (7, 7, one("LIBRARY"))],
    "Tue": [(1, 2, [("DSA_LAB", "D1"), ("CPP_LAB", "D2")]),
            (3, 3, one("CS302")), (4, 4, one("MCS301")), (5, 5, one("CS305")),
            (6, 6, one("CS304")), (7, 7, one("CSP308"))],
    "Wed": [(1, 2, [("DSA_LAB", "D2"), ("CPP_LAB", "D1")]),
            (3, 3, one("CS302")), (4, 4, one("MCS301")), (5, 5, one("CS305")),
            (6, 6, one("CS304")), (7, 7, one("NCK310"))],
    "Thu": [(1, 1, one("CS303")), (2, 2, one("CS303")),
            (3, 4, [("SKL300", "D1"), ("DDCO_LAB", "D2")]),
            (5, 5, one("MCS301")), (6, 6, one("CS302")), (7, 7, one("TUTORIAL"))],
    "Fri": [(1, 1, one("CS303")), (2, 2, one("CS303")), (3, 3, one("CS304")),
            (4, 4, one("CS305")), (5, 6, one("MAD309")), (7, 7, one("LIBRARY"))],
    "Sat": [(1, 1, one("CS305")), (2, 2, one("CS304")), (3, 3, one("CS303")),
            (4, 4, one("CS302")), (5, 7, one("AICTE"))],
}

with db() as c:
    # Expertise = subject codes a teacher can cover, used by the optimizer.
    # OWN comes straight from the timetable. GUESS is an invented sample so the optimizer
    # has someone to pick in tests - REPLACE with the real list from the HOD.
    OWN = {}
    for code, _name, abbrev, _kind in SUBJECTS.values():
        if abbrev and code:
            OWN.setdefault(abbrev, set()).add(code)
    GUESS = {"KI": {"B25CS305", "B25CSL307"}, "IS": {"B25CS302", "B25CSL306"},
             "ASP": {"B25MAD309"}, "GM": {"B25MCS301"}}
    ids = {}
    for name, abbrev in FACULTY:
        expertise = ",".join(sorted(OWN.get(abbrev, set()) | GUESS.get(abbrev, set())))
        cur = c.execute("INSERT INTO faculty(name,abbrev,max_hours,expertise) VALUES(?,?,?,?)",
                        (name, abbrev, DEFAULT_MAX_HOURS, expertise))
        ids[abbrev] = cur.lastrowid
    for p, start, end in PERIODS:
        c.execute("INSERT INTO periods(period,start_time,end_time) VALUES(?,?,?)", (p, start, end))
    rows = 0
    for day, blocks in SCHEDULE.items():
        for first, last, entries in blocks:
            for period in range(first, last + 1):
                for key, batch in entries:
                    code, name, abbrev, kind = SUBJECTS[key]
                    c.execute("""INSERT INTO timetable(day,period,class_name,subject,subject_code,
                                 room,batch,slot_type,faculty_id) VALUES(?,?,?,?,?,?,?,?,?)""",
                              (day, period, CLASS_NAME, name, code, ROOM, batch, kind, ids.get(abbrev)))
                    rows += 1

print(f"Seeded: {len(FACULTY)} faculty, {len(PERIODS)} periods, {rows} timetable rows")
