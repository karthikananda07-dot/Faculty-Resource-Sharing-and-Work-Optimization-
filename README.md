# Faculty Resource Sharing & Workload Optimizer (Frontend)

Static frontend (HTML + Tailwind CDN + vanilla JS). Currently runs on in-browser
data (localStorage). The backend team will replace that with real API calls.

## Run locally
1. Clone the repo.
2. Open the folder in VS Code and run `index.html` with the **Live Server** extension
   (or just double-click `index.html`). Internet is needed for the CDN libraries.

## Folder structure
```
index.html      page layout (tabs, forms, modals)
css/style.css   custom styles
js/app.js       all app logic
```

## Roles (demo login, no passwords yet)
| Role    | Can do |
|---------|--------|
| admin   | everything |
| hod     | assign tasks, run optimizer, add resources, manage timetable, answer cover requests |
| faculty | book resources, request cover for own classes, answer cover requests sent to them |

## Where the frontend touches data (for backend integration)
All state lives in one object `S` in `js/app.js`:
`S = { faculty, resources, logs, timetable, covers, notes }`

| Frontend function | Replace with API call |
|---|---|
| `load()` / `save()` | initial GET of all collections / remove (server is the source of truth) |
| `addFaculty`, `removeFaculty` | `POST` / `DELETE /api/faculty` |
| `addTask`, `removeTask` | `POST` / `DELETE /api/faculty/:id/tasks` |
| `addResource`, `removeResource` | `POST` / `DELETE /api/resources` |
| `confirmBooking`, `cancelBooking` | `POST` / `DELETE /api/resources/:id/bookings` |
| `previewOptimize` / `applyOptimize` | `POST /api/optimizer/preview` and `/apply` (or keep logic client-side) |
| `addSlot`, `delSlot` | `POST` / `DELETE /api/timetable` |
| `sendCover`, `answerCover` | `POST /api/covers`, `PATCH /api/covers/:id` |
| `notify`, `mine` | `GET /api/notifications` (server creates them) |
| `doLogin`, `logout` | `POST /api/auth/login`, `/logout` (replace the demo role picker) |

## Data shapes the frontend expects
```json
Faculty:   { "id": 1, "name": "", "department": "", "maxCapacity": 40, "expertise": "",
             "tasks": [ { "id": 1, "title": "", "type": "Lecture|Lab Duty|Research|Admin Work", "hours": 10 } ] }
Resource:  { "id": 1, "name": "", "category": "", "department": "",
             "bookings": [ { "id": 1, "by": "Faculty name", "date": "YYYY-MM-DD", "slot": "09:00-11:00" } ] }
Timetable: { "id": 1, "fid": 1, "day": "Mon|Tue|Wed|Thu|Fri", "slot": "09:00-11:00", "title": "" }
Cover:     { "id": 1, "slotId": 1, "fromId": 1, "toId": 2, "why": "", "status": "Pending|Accepted|Declined" }
Notification: { "id": 1, "to": 1, "text": "", "read": false, "ts": "" }   // "to" = faculty id, or "mgr" for admin/HOD
```
Time slots: `09:00-11:00`, `11:00-13:00`, `14:00-16:00`, `16:00-18:00`.
Departments and categories are the lists `DEPTS` and `CATS` at the top of `js/app.js`.

## Known limitations
- Demo login only; real authentication must come from the backend.
- Business rules (booking clashes, timetable clashes) are checked in the browser;
  the backend should enforce them too.
- No document/file sharing yet.
