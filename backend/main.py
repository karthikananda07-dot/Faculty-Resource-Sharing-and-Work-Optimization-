from optimizer.substitute_solver import optimize_substitutes
import json
import sqlite3
import datetime as dt
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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
            max_hours INTEGER DEFAULT 18);
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
            faculty_id INTEGER NOT NULL REFERENCES faculty(id));
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


init_db()



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



def day_of(date_str: str) -> str:
    try:
        return dt.date.fromisoformat(date_str).strftime("%a")  # Mon, Tue...
    except ValueError:
        raise HTTPException(400, "date must be YYYY-MM-DD")


def free_faculty(c, date: str, period: int):
    day = day_of(date)
    rows = c.execute("""
        SELECT * FROM faculty WHERE id NOT IN (
            SELECT faculty_id FROM timetable WHERE day=? AND period=?)
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


@app.get("/faculty")
def list_faculty():
    with db() as c:
        return [dict(r) for r in c.execute("SELECT * FROM faculty")]


@app.post("/faculty")
def add_faculty(f: FacultyIn):
    with db() as c:
        cur = c.execute("INSERT INTO faculty(name,email,subject,max_hours) VALUES(?,?,?,?)",
                        (f.name, f.email, f.subject, f.max_hours))
        return {"id": cur.lastrowid, **f.model_dump()}


@app.get("/timetable")
def timetable(day: str | None = None, faculty_id: int | None = None):
    q = """SELECT t.*, f.name AS faculty_name FROM timetable t
           JOIN faculty f ON f.id=t.faculty_id WHERE 1=1"""
    args = []
    if day:
        q += " AND t.day=?"; args.append(day)
    if faculty_id:
        q += " AND t.faculty_id=?"; args.append(faculty_id)
    q += " ORDER BY t.day, t.period"
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
# ---------- OR-Tools substitute optimizer ----------
class OptimizeSubstitutesIn(BaseModel):
    faculty_id: int
    date: str


@app.post("/optimize-substitutes")
def optimize_substitutes_endpoint(request: OptimizeSubstitutesIn):
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

        faculty = [
            dict(r) for r in c.execute("SELECT * FROM faculty")
        ]

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

        # Add the date and available substitutes expected by the solver.
        for slot in slots:
            slot["date"] = request.date
            slot["available_substitutes"] = free_faculty(
                c, request.date, slot["period"]
            )

    recommendations = optimize_substitutes(
        slots, faculty, weekly_hours
    )

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
