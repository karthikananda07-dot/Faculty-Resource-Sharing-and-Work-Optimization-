import json
import sqlite3
import datetime as dt
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

try:  # OR-Tools optimizer lives in backend/optimizer/ (needs: pip install -r requirements.txt)
    from optimizer.substitute_solver import optimize_substitutes
except ImportError:
    optimize_substitutes = None

DB = "dept.db"
PERIODS = range(1, 7)

app = FastAPI(title="Dept Project API")
app.add_middleware(CORSMiddleware, allow_origins=["*"],
                   allow_methods=["*"], allow_headers=["*"])


def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def init_db():
    with db() as c:
        c.executescript("""
        CREATE TABLE IF NOT EXISTS faculty(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL, email TEXT, subject TEXT,
            max_hours INTEGER DEFAULT 18, abbrev TEXT, expertise TEXT);
        CREATE TABLE IF NOT EXISTS periods(
            period INTEGER PRIMARY KEY, start_time TEXT, end_time TEXT);
        CREATE TABLE IF NOT EXISTS assignments(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL, period INTEGER NOT NULL, class_name TEXT NOT NULL,
            faculty_id INTEGER NOT NULL REFERENCES faculty(id),
            source TEXT DEFAULT 'optimizer',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS timetable(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            day TEXT NOT NULL, period INTEGER NOT NULL,
            class_name TEXT NOT NULL, subject TEXT, room TEXT,
            subject_code TEXT, batch TEXT, slot_type TEXT DEFAULT 'class',
            faculty_id INTEGER REFERENCES faculty(id));  -- NULL = free/non-teaching slot
        CREATE TABLE IF NOT EXISTS absences(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            faculty_id INTEGER NOT NULL REFERENCES faculty(id),
            date TEXT NOT NULL, reason TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS exchanges(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            date TEXT NOT NULL, period INTEGER NOT NULL, class_name TEXT NOT NULL,
            from_faculty INTEGER NOT NULL REFERENCES faculty(id),
            to_faculty INTEGER NOT NULL REFERENCES faculty(id),
            status TEXT DEFAULT 'pending',
            created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS updates(
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            type TEXT, message TEXT, data TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP);
        """)
        cols = [r["name"] for r in c.execute("PRAGMA table_info(faculty)")]
        if "max_hours" not in cols:  # upgrade an older dept.db
            c.execute("ALTER TABLE faculty ADD COLUMN max_hours INTEGER DEFAULT 18")
        if "abbrev" not in cols:
            c.execute("ALTER TABLE faculty ADD COLUMN abbrev TEXT")
        if "expertise" not in cols:
            c.execute("ALTER TABLE faculty ADD COLUMN expertise TEXT")


init_db()


# ---------- live updates ----------
class Hub:
    def __init__(self):
        self.clients = set()

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self.clients.add(ws)

    def disconnect(self, ws: WebSocket):
        self.clients.discard(ws)

    async def broadcast(self, event: dict):
        for ws in list(self.clients):
            try:
                await ws.send_json(event)
            except Exception:
                self.clients.discard(ws)


hub = Hub()


async def publish(type_: str, message: str, data: dict):
    with db() as c:
        cur = c.execute("INSERT INTO updates(type,message,data) VALUES(?,?,?)",
                        (type_, message, json.dumps(data)))
        uid = cur.lastrowid
    await hub.broadcast({"id": uid, "type": type_, "message": message,
                         "data": data,
                         "time": dt.datetime.now().isoformat(timespec="seconds")})


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket):
    await hub.connect(ws)
    try:
        while True:
            await ws.receive_text()  # keep-alive
    except WebSocketDisconnect:
        hub.disconnect(ws)


# ---------- helpers ----------
def day_of(date_str: str) -> str:
    try:
        return dt.date.fromisoformat(date_str).strftime("%a")  # Mon, Tue...
    except ValueError:
        raise HTTPException(400, "date must be YYYY-MM-DD")


def free_faculty(c, date: str, period: int):
    day = day_of(date)
    rows = c.execute("""
        SELECT * FROM faculty WHERE id NOT IN (
            SELECT faculty_id FROM timetable
            WHERE day=? AND period=? AND faculty_id IS NOT NULL)
        AND id NOT IN (SELECT faculty_id FROM absences WHERE date=?)
        AND id NOT IN (SELECT to_faculty FROM exchanges
                       WHERE date=? AND period=? AND status='accepted')
    """, (day, period, date, date, period)).fetchall()
    return [dict(r) for r in rows]


# ---------- faculty & timetable ----------
class FacultyIn(BaseModel):
    name: str
    email: str | None = None
    subject: str | None = None
    max_hours: int = 18
    abbrev: str | None = None
    expertise: str | None = None   # subject codes this teacher can cover, e.g. "B25CS302,B25CSL306"


@app.get("/faculty")
def list_faculty():
    with db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM faculty")]


@app.post("/faculty")
def add_faculty(f: FacultyIn):
    with db() as c:
        cur = c.execute("INSERT INTO faculty(name,email,subject,max_hours,abbrev,expertise) VALUES(?,?,?,?,?,?)",
                        (f.name, f.email, f.subject, f.max_hours, f.abbrev, f.expertise))
        return {"id": cur.lastrowid, **f.model_dump()}


@app.get("/timetable")
def timetable(day: str | None = None, faculty_id: int | None = None):
    q = """SELECT t.*, f.name AS faculty_name, f.abbrev AS faculty_abbrev
           FROM timetable t LEFT JOIN faculty f ON f.id=t.faculty_id WHERE 1=1"""
    args = []
    if day:
        q += " AND t.day=?"; args.append(day)
    if faculty_id:
        q += " AND t.faculty_id=?"; args.append(faculty_id)
    q += " ORDER BY instr('MonTueWedThuFriSat', t.day), t.period"
    with db() as c:
        return [dict(r) for r in c.execute(q, args)]


# ---------- absences ----------
class AbsenceIn(BaseModel):
    faculty_id: int
    date: str
    reason: str | None = None


@app.post("/absences")
async def mark_absent(a: AbsenceIn):
    day = day_of(a.date)
    with db() as c:
        fac = c.execute("SELECT * FROM faculty WHERE id=?", (a.faculty_id,)).fetchone()
        if not fac:
            raise HTTPException(404, "faculty not found")
        c.execute("INSERT INTO absences(faculty_id,date,reason) VALUES(?,?,?)",
                  (a.faculty_id, a.date, a.reason))
        slots = [dict(r) for r in c.execute(
            "SELECT * FROM timetable WHERE faculty_id=? AND day=? ORDER BY period",
            (a.faculty_id, day))]
        for s in slots:
            s["available_substitutes"] = free_faculty(c, a.date, s["period"])
    await publish("absence", f"{fac['name']} is absent on {a.date}",
                  {"faculty_id": a.faculty_id, "date": a.date,
                   "reason": a.reason, "affected_classes": slots})
    return {"affected_classes": slots}


@app.get("/absences")
def list_absences(date: str | None = None):
    q = """SELECT a.*, f.name AS faculty_name FROM absences a
           JOIN faculty f ON f.id=a.faculty_id"""
    args = []
    if date:
        q += " WHERE a.date=?"; args.append(date)
    with db() as c:
        return [dict(r) for r in c.execute(q, args)]


# ---------- class exchanges ----------
class ExchangeIn(BaseModel):
    date: str
    period: int
    class_name: str
    from_faculty: int
    to_faculty: int


class ExchangeReply(BaseModel):
    accept: bool


@app.post("/exchanges")
async def request_exchange(e: ExchangeIn):
    with db() as c:
        if e.to_faculty not in [f["id"] for f in free_faculty(c, e.date, e.period)]:
            raise HTTPException(409, "that faculty is not free in this period")
        names = {r["id"]: r["name"] for r in c.execute(
            "SELECT id,name FROM faculty WHERE id IN (?,?)",
            (e.from_faculty, e.to_faculty))}
        cur = c.execute("""INSERT INTO exchanges(date,period,class_name,from_faculty,to_faculty)
                           VALUES(?,?,?,?,?)""",
                        (e.date, e.period, e.class_name, e.from_faculty, e.to_faculty))
        eid = cur.lastrowid
    await publish("exchange_request",
                  f"{names.get(e.from_faculty)} asked {names.get(e.to_faculty)} to take "
                  f"{e.class_name} (period {e.period}, {e.date})",
                  {"exchange_id": eid, **e.model_dump()})
    return {"exchange_id": eid, "status": "pending"}


@app.post("/exchanges/{eid}/respond")
async def respond_exchange(eid: int, r: ExchangeReply):
    status = "accepted" if r.accept else "rejected"
    with db() as c:
        row = c.execute("SELECT * FROM exchanges WHERE id=?", (eid,)).fetchone()
        if not row:
            raise HTTPException(404, "exchange not found")
        if row["status"] != "pending":
            raise HTTPException(409, f"already {row['status']}")
        c.execute("UPDATE exchanges SET status=? WHERE id=?", (status, eid))
    await publish(f"exchange_{status}",
                  f"Exchange #{eid} {status} ({row['class_name']}, period {row['period']}, {row['date']})",
                  {"exchange_id": eid, "status": status})
    return {"exchange_id": eid, "status": status}


@app.get("/exchanges")
def list_exchanges(status: str | None = None):
    q = "SELECT * FROM exchanges"
    args = []
    if status:
        q += " WHERE status=?"; args.append(status)
    with db() as c:
        return [dict(r) for r in c.execute(q + " ORDER BY id DESC", args)]


# ---------- feed ----------
@app.get("/updates")
def updates(limit: int = 50):
    with db() as c:
        rows = c.execute("SELECT * FROM updates ORDER BY id DESC LIMIT ?", (limit,))
        return [{**dict(r), "data": json.loads(r["data"] or "{}")} for r in rows]


# ---------- workload + optimizer integration ----------
@app.get("/workload")
def workload():
    """Weekly teaching hours per teacher vs their max_hours (input for the optimizer)."""
    with db() as c:
        rows = c.execute("""
            SELECT f.id, f.name, f.subject, f.max_hours,
                   COUNT(t.id) AS weekly_hours
            FROM faculty f LEFT JOIN timetable t ON t.faculty_id = f.id
            GROUP BY f.id""")
        out = []
        for r in rows:
            d = dict(r)
            d["remaining_hours"] = d["max_hours"] - d["weekly_hours"]
            out.append(d)
        return out


class AssignmentIn(BaseModel):
    date: str
    period: int
    class_name: str
    faculty_id: int


@app.post("/assignments")
async def save_assignments(items: list[AssignmentIn]):
    """The optimizer posts its suggested substitutes here; teachers get a live update."""
    saved = []
    with db() as c:
        for a in items:
            day_of(a.date)  # validates date format
            fac = c.execute("SELECT name FROM faculty WHERE id=?", (a.faculty_id,)).fetchone()
            if not fac:
                raise HTTPException(404, f"faculty {a.faculty_id} not found")
            cur = c.execute("""INSERT INTO assignments(date,period,class_name,faculty_id)
                               VALUES(?,?,?,?)""",
                            (a.date, a.period, a.class_name, a.faculty_id))
            saved.append({"id": cur.lastrowid, "faculty_name": fac["name"], **a.model_dump()})
    for s in saved:
        await publish("assignment",
                      f"{s['faculty_name']} assigned to {s['class_name']} "
                      f"(period {s['period']}, {s['date']})", s)
    return {"saved": saved}


@app.get("/assignments")
def list_assignments(date: str | None = None):
    q = """SELECT a.*, f.name AS faculty_name FROM assignments a
           JOIN faculty f ON f.id=a.faculty_id"""
    args = []
    if date:
        q += " WHERE a.date=?"; args.append(date)
    with db() as c:
        return [dict(r) for r in c.execute(q + " ORDER BY a.id DESC", args)]


# ---------- periods + admin edits (for the frontend's edit forms) ----------
DAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat")


@app.get("/periods")
def periods():
    with db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM periods ORDER BY period")]


@app.put("/faculty/{fid}")
def update_faculty(fid: int, f: FacultyIn):
    with db() as c:
        cur = c.execute("""UPDATE faculty SET name=?, email=?, subject=?, max_hours=?, abbrev=?, expertise=?
                           WHERE id=?""",
                        (f.name, f.email, f.subject, f.max_hours, f.abbrev, f.expertise, fid))
        if cur.rowcount == 0:
            raise HTTPException(404, "faculty not found")
    return {"id": fid, **f.model_dump()}


class SlotIn(BaseModel):
    day: str
    period: int
    class_name: str
    subject: str | None = None
    subject_code: str | None = None
    room: str | None = None
    batch: str | None = None
    slot_type: str = "class"          # class | lab | free
    faculty_id: int | None = None     # leave empty for Library, Mentoring, etc.


def check_slot(c, s: SlotIn, exclude_id: int = 0):
    if s.day not in DAYS:
        raise HTTPException(400, "day must be one of Mon, Tue, Wed, Thu, Fri, Sat")
    if s.faculty_id is not None:
        if not c.execute("SELECT 1 FROM faculty WHERE id=?", (s.faculty_id,)).fetchone():
            raise HTTPException(404, "faculty not found")
        clash = c.execute("""SELECT class_name FROM timetable
                             WHERE day=? AND period=? AND faculty_id=? AND id<>?""",
                          (s.day, s.period, s.faculty_id, exclude_id)).fetchone()
        if clash:
            raise HTTPException(409, f"teacher already teaches {clash['class_name']} in this period")


SLOT_COLS = "day,period,class_name,subject,subject_code,room,batch,slot_type,faculty_id"


def slot_values(s: SlotIn):
    return (s.day, s.period, s.class_name, s.subject, s.subject_code,
            s.room, s.batch, s.slot_type, s.faculty_id)


@app.post("/timetable")
async def add_slot(s: SlotIn):
    with db() as c:
        check_slot(c, s)
        cur = c.execute(f"INSERT INTO timetable({SLOT_COLS}) VALUES(?,?,?,?,?,?,?,?,?)", slot_values(s))
        sid = cur.lastrowid
    await publish("timetable_changed",
                  f"Timetable updated: {s.class_name}, {s.day} period {s.period}",
                  {"slot_id": sid, **s.model_dump()})
    return {"id": sid, **s.model_dump()}


@app.put("/timetable/{sid}")
async def update_slot(sid: int, s: SlotIn):
    with db() as c:
        if not c.execute("SELECT 1 FROM timetable WHERE id=?", (sid,)).fetchone():
            raise HTTPException(404, "slot not found")
        check_slot(c, s, sid)
        c.execute("""UPDATE timetable SET day=?,period=?,class_name=?,subject=?,subject_code=?,
                     room=?,batch=?,slot_type=?,faculty_id=? WHERE id=?""", slot_values(s) + (sid,))
    await publish("timetable_changed",
                  f"Timetable updated: {s.class_name}, {s.day} period {s.period}",
                  {"slot_id": sid, **s.model_dump()})
    return {"id": sid, **s.model_dump()}


@app.delete("/timetable/{sid}")
async def delete_slot(sid: int):
    with db() as c:
        row = c.execute("SELECT * FROM timetable WHERE id=?", (sid,)).fetchone()
        if not row:
            raise HTTPException(404, "slot not found")
        c.execute("DELETE FROM timetable WHERE id=?", (sid,))
    await publish("timetable_changed",
                  f"Timetable updated: {row['class_name']}, {row['day']} period {row['period']} removed",
                  {"slot_id": sid, "deleted": True})
    return {"deleted": sid}


# ---------- OR-Tools substitute optimizer (from the integrate-optimizer branch) ----------
class OptimizeSubstitutesIn(BaseModel):
    faculty_id: int
    date: str


def qualified_for(f: dict, slot: dict) -> bool:
    """A teacher can cover a class if its subject code is in their `expertise` list."""
    codes = {x.strip() for x in (f.get("expertise") or "").split(",") if x.strip()}
    return bool(slot.get("subject_code")) and slot["subject_code"] in codes


@app.post("/optimize-substitutes")
def optimize_substitutes_endpoint(request: OptimizeSubstitutesIn):
    if optimize_substitutes is None:
        raise HTTPException(503, "Optimizer not installed: add the optimizer folder and run "
                                 "pip install -r requirements.txt")
    day = day_of(request.date)

    with db() as c:
        # Confirm that this faculty member has been recorded as absent.
        absence = c.execute(
            "SELECT id FROM absences WHERE faculty_id=? AND date=?",
            (request.faculty_id, request.date)
        ).fetchone()

        if not absence:
            raise HTTPException(
                404,
                "Record this faculty absence first using POST /absences."
            )

        faculty = [dict(r) for r in c.execute("SELECT * FROM faculty")]

        # Calculate current weekly teaching hours from the timetable.
        weekly_hours = {
            r["id"]: r["weekly_hours"]
            for r in c.execute("""
                SELECT f.id, COUNT(t.id) AS weekly_hours
                FROM faculty f
                LEFT JOIN timetable t ON t.faculty_id = f.id
                GROUP BY f.id
            """)
        }

        # Find the absent faculty member's affected classes.
        slots = [
            dict(r) for r in c.execute("""
                SELECT * FROM timetable
                WHERE faculty_id=? AND day=?
                ORDER BY period
            """, (request.faculty_id, day))
        ]

        # Add the date and the free teachers who are qualified for each class.
        # The solver matches `candidate["subject"] == slot["subject"]`, so qualified
        # teachers are passed in with that subject set to the class's subject.
        for slot in slots:
            slot["date"] = request.date
            slot["available_substitutes"] = [
                {**f, "subject": slot["subject"]}
                for f in free_faculty(c, request.date, slot["period"])
                if qualified_for(f, slot)
            ]

    recommendations = optimize_substitutes(slots, faculty, weekly_hours)

    return {
        "date": request.date,
        "absent_faculty_id": request.faculty_id,
        "recommendations": recommendations,
        "saved": False,
        "message": (
            "Recommendations generated for review. "
            "No assignments have been saved."
        )
    }
