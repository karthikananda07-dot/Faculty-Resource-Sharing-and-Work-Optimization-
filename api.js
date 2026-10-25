/* =====================================================================
   api.js  -  the ONLY file that talks to storage or the backend.
   Backend team: set CONFIG.USE_BACKEND = true, set BASE_URL, and make
   your API return the JSON shapes described in README.md.
   In local mode (default) data is kept in the browser's localStorage and
   every per-action call below is a harmless no-op.
   ===================================================================== */
const API = (() => {
  const CONFIG = {
    USE_BACKEND: false,
    BASE_URL: "http://localhost:5000/api",
    STORAGE_KEY: "frwo-state-v1"
  };

  async function http(method, path, body) {
    const res = await fetch(CONFIG.BASE_URL + path, {
      method,
      headers: { "Content-Type": "application/json" },
      credentials: "include", // send session cookie; swap for a Bearer token if you use JWT
      body: body === undefined ? undefined : JSON.stringify(body)
    });
    if (!res.ok) throw new Error(`${method} ${path} failed (${res.status})`);
    return res.status === 204 ? null : res.json();
  }
  // Local mode: resolve with null. Backend mode: real request.
  const call = (method, path, body) => CONFIG.USE_BACKEND ? http(method, path, body) : Promise.resolve(null);

  return {
    CONFIG,

    /* ---- load / persist ---- */
    // Must resolve to { faculty, resources, timetable, covers, notes, logs } or null.
    async loadAll() {
      if (CONFIG.USE_BACKEND) {
        const get = p => http("GET", "/" + p);
        const [faculty, resources, timetable, covers, notes, logs] =
          await Promise.all(["faculty", "resources", "timetable", "covers", "notifications", "activity"].map(get));
        return { faculty, resources, timetable, covers, notes, logs };
      }
      try { const d = localStorage.getItem(CONFIG.STORAGE_KEY); return d ? JSON.parse(d) : null; }
      catch (e) { return null; }
    },
    saveLocal(state) { // only used in local mode
      if (CONFIG.USE_BACKEND) return;
      try { localStorage.setItem(CONFIG.STORAGE_KEY, JSON.stringify(state)); } catch (e) {}
    },

    /* ---- auth ---- */
    login: user => call("POST", "/auth/login", user),          // user = { role, fid }
    logout: () => call("POST", "/auth/logout"),

    /* ---- faculty & tasks (create calls may return the saved object with its real id) ---- */
    addFaculty: f => call("POST", "/faculty", f),
    removeFaculty: id => call("DELETE", `/faculty/${id}`),
    addTask: (facultyId, t) => call("POST", `/faculty/${facultyId}/tasks`, t),
    removeTask: (facultyId, taskId) => call("DELETE", `/faculty/${facultyId}/tasks/${taskId}`),

    /* ---- optimizer ---- */
    applyOptimization: moves => call("POST", "/optimizer/apply", { moves }), // [{tid,title,hours,from,to}]
    undoOptimization: () => call("POST", "/optimizer/undo"),

    /* ---- resources & bookings ---- */
    addResource: r => call("POST", "/resources", r),
    removeResource: id => call("DELETE", `/resources/${id}`),
    addBooking: (resourceId, b) => call("POST", `/resources/${resourceId}/bookings`, b),
    removeBooking: (resourceId, bookingId) => call("DELETE", `/resources/${resourceId}/bookings/${bookingId}`),

    /* ---- timetable & cover requests ---- */
    addSlot: s => call("POST", "/timetable", s),
    removeSlot: id => call("DELETE", `/timetable/${id}`),
    addCover: c => call("POST", "/covers", c),
    answerCover: (id, status) => call("PATCH", `/covers/${id}`, { status }), // "Accepted" | "Declined"

    /* ---- notifications & activity log (backend may create these itself and ignore these calls) ---- */
    addNotification: n => call("POST", "/notifications", n),
    markNotificationsRead: ids => call("PATCH", "/notifications/read", { ids }),
    addLog: text => call("POST", "/activity", { text })
  };
})();
