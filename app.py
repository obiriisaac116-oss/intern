import sqlite3
import os
from flask import Flask, request, jsonify, render_template
from datetime import datetime, date, timezone

app = Flask(__name__)
# On Render the DB_PATH env var points to /data/tracker.db (persistent disk).
# Locally it falls back to tracker.db next to this file.
DB_PATH = os.environ.get(
    "DB_PATH",
    os.path.join(os.path.dirname(__file__), "tracker.db"),
)


# ---------------------------------------------------------------------------
# Database helpers
# ---------------------------------------------------------------------------

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db():
    with get_db() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS interns (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                name       TEXT    NOT NULL UNIQUE COLLATE NOCASE,
                start_date TEXT,
                end_date   TEXT,
                created_at TEXT    NOT NULL DEFAULT (datetime('now'))
            );

            -- Every time someone is checked in a row is created.
            -- checked_out_at is NULL while they are still here.
            CREATE TABLE IF NOT EXISTS checkins (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                intern_id      INTEGER NOT NULL REFERENCES interns(id) ON DELETE CASCADE,
                checked_in_at  TEXT    NOT NULL DEFAULT (datetime('now')),
                checked_out_at TEXT
            );
        """)
        # Migrate existing tables that may not have start_date / end_date
        cols = [r[1] for r in conn.execute("PRAGMA table_info(interns)").fetchall()]
        if "start_date" not in cols:
            conn.execute("ALTER TABLE interns ADD COLUMN start_date TEXT")
        if "end_date" not in cols:
            conn.execute("ALTER TABLE interns ADD COLUMN end_date TEXT")


def today_str():
    return date.today().isoformat()   # "YYYY-MM-DD"


def _auto_expire():
    """
    Checkout anyone still checked in whose internship end_date has passed.
    Called before returning 'here' data so the list is always accurate.
    """
    today = today_str()
    now   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        conn.execute(
            """UPDATE checkins SET checked_out_at=?
               WHERE checked_out_at IS NULL
               AND intern_id IN (
                   SELECT id FROM interns
                   WHERE end_date IS NOT NULL AND end_date < ?
               )""",
            (now, today),
        )


def _duration_stats(start_date_str, end_date_str):
    """
    Given ISO date strings (or None), return a dict with:
      days_elapsed, days_remaining, weeks_remaining, months_remaining,
      pct_complete, status  ('upcoming' | 'active' | 'ended' | 'unknown')
    """
    today = date.today()
    stats = {
        "days_elapsed": None, "days_remaining": None,
        "weeks_remaining": None, "months_remaining": None,
        "pct_complete": None, "status": "unknown",
    }
    if not start_date_str:
        return stats
    try:
        start = date.fromisoformat(start_date_str)
        end   = date.fromisoformat(end_date_str) if end_date_str else None
    except ValueError:
        return stats

    if today < start:
        stats["status"] = "upcoming"
        stats["days_elapsed"] = 0
        if end:
            total = (end - start).days
            stats["days_remaining"]  = total
            stats["weeks_remaining"] = round(total / 7, 1)
            stats["months_remaining"] = round(total / 30.44, 1)
            stats["pct_complete"] = 0
        return stats

    stats["days_elapsed"] = (today - start).days

    if end:
        if today > end:
            stats["status"] = "ended"
            stats["days_remaining"]  = 0
            stats["weeks_remaining"] = 0
            stats["months_remaining"] = 0
            total = max((end - start).days, 1)
            stats["pct_complete"] = 100
        else:
            stats["status"] = "active"
            remaining = (end - today).days
            total     = (end - start).days
            stats["days_remaining"]   = remaining
            stats["weeks_remaining"]  = round(remaining / 7, 1)
            stats["months_remaining"] = round(remaining / 30.44, 1)
            stats["pct_complete"]     = round((stats["days_elapsed"] / max(total, 1)) * 100)
    else:
        stats["status"] = "active"

    return stats


# ---------------------------------------------------------------------------
# Ensure DB is initialized on every cold start
# ---------------------------------------------------------------------------

with app.app_context():
    init_db()


# ---------------------------------------------------------------------------
# Page
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    return render_template("index.html")


# ---------------------------------------------------------------------------
# Interns CRUD
# ---------------------------------------------------------------------------

@app.route("/api/interns", methods=["GET"])
def list_interns():
    q = request.args.get("q", "").strip()
    with get_db() as conn:
        if q:
            rows = conn.execute(
                """SELECT i.*, COUNT(c.id) AS visit_count
                   FROM interns i
                   LEFT JOIN checkins c ON c.intern_id = i.id
                   WHERE i.name LIKE ?
                   GROUP BY i.id ORDER BY i.name""",
                (f"%{q}%",),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT i.*, COUNT(c.id) AS visit_count
                   FROM interns i
                   LEFT JOIN checkins c ON c.intern_id = i.id
                   GROUP BY i.id ORDER BY i.name"""
            ).fetchall()
    result = []
    for r in rows:
        d = dict(r)
        d.update(_duration_stats(d.get("start_date"), d.get("end_date")))
        result.append(d)
    return jsonify(result)


@app.route("/api/interns", methods=["POST"])
def create_intern():
    data = request.get_json(force=True)
    name       = (data.get("name") or "").strip()
    start_date = (data.get("start_date") or "").strip() or None
    end_date   = (data.get("end_date")   or "").strip() or None
    if not name:
        return jsonify({"error": "name is required"}), 400

    with get_db() as conn:
        existing = conn.execute(
            "SELECT id FROM interns WHERE LOWER(name)=LOWER(?)", (name,)
        ).fetchone()
        if existing:
            return jsonify({"error": f'"{name}" is already registered'}), 409

        cur = conn.execute(
            "INSERT INTO interns (name, start_date, end_date) VALUES (?,?,?)",
            (name, start_date, end_date),
        )
        iid = cur.lastrowid
        row = conn.execute(
            "SELECT *, 0 AS visit_count FROM interns WHERE id=?", (iid,)
        ).fetchone()
    d = dict(row)
    d.update(_duration_stats(d.get("start_date"), d.get("end_date")))
    return jsonify(d), 201


@app.route("/api/interns/<int:iid>", methods=["PUT"])
def update_intern(iid):
    data = request.get_json(force=True)
    name       = (data.get("name") or "").strip()
    start_date = (data.get("start_date") or "").strip() or None
    end_date   = (data.get("end_date")   or "").strip() or None
    if not name:
        return jsonify({"error": "name is required"}), 400
    with get_db() as conn:
        conn.execute(
            "UPDATE interns SET name=?, start_date=?, end_date=? WHERE id=?",
            (name, start_date, end_date, iid),
        )
        row = conn.execute(
            """SELECT i.*, COUNT(c.id) AS visit_count
               FROM interns i LEFT JOIN checkins c ON c.intern_id=i.id
               WHERE i.id=? GROUP BY i.id""", (iid,)
        ).fetchone()
    if not row:
        return jsonify({"error": "Not found"}), 404
    d = dict(row)
    d.update(_duration_stats(d.get("start_date"), d.get("end_date")))
    return jsonify(d)


@app.route("/api/interns/<int:iid>", methods=["DELETE"])
def delete_intern(iid):
    with get_db() as conn:
        conn.execute("DELETE FROM interns WHERE id=?", (iid,))
    return jsonify({"ok": True})


@app.route("/api/interns/<int:iid>/renew", methods=["POST"])
def renew_intern(iid):
    """
    Set new start_date / end_date for a returning intern whose period has ended.
    Clears the old dates and lets the intern start a fresh period.
    """
    data       = request.get_json(force=True)
    start_date = (data.get("start_date") or "").strip() or None
    end_date   = (data.get("end_date")   or "").strip() or None

    if not start_date:
        return jsonify({"error": "start_date is required"}), 400

    with get_db() as conn:
        row = conn.execute("SELECT id FROM interns WHERE id=?", (iid,)).fetchone()
        if not row:
            return jsonify({"error": "Intern not found"}), 404

        conn.execute(
            "UPDATE interns SET start_date=?, end_date=? WHERE id=?",
            (start_date, end_date, iid),
        )
        updated = conn.execute(
            """SELECT i.*, COUNT(c.id) AS visit_count
               FROM interns i LEFT JOIN checkins c ON c.intern_id=i.id
               WHERE i.id=? GROUP BY i.id""",
            (iid,),
        ).fetchone()

    d = dict(updated)
    d.update(_duration_stats(d.get("start_date"), d.get("end_date")))
    return jsonify(d)


# ---------------------------------------------------------------------------
# Lookup — called as user types (fuzzy, returns visit history hint)
# ---------------------------------------------------------------------------

@app.route("/api/lookup", methods=["GET"])
def lookup():
    """
    Fuzzy name search. Returns matches with:
      - visit_count  : total past check-ins
      - is_here      : currently checked in today (not yet checked out)
      - visit_message: human-readable "Xth time" string
    """
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])

    today = today_str()

    with get_db() as conn:
        rows = conn.execute(
            """SELECT i.*, COUNT(c.id) AS visit_count
               FROM interns i
               LEFT JOIN checkins c ON c.intern_id = i.id
               WHERE i.name LIKE ?
               GROUP BY i.id
               ORDER BY i.name
               LIMIT 8""",
            (f"%{q}%",),
        ).fetchall()

        results = []
        for row in rows:
            p = dict(row)

            # Is this person currently checked in right now?
            active = conn.execute(
                """SELECT id FROM checkins
                   WHERE intern_id=? AND date(checked_in_at)=? AND checked_out_at IS NULL""",
                (p["id"], today),
            ).fetchone()
            p["is_here"] = active is not None
            p["active_checkin_id"] = active["id"] if active else None

            count = p["visit_count"]
            next_n = count + 1
            if count == 0:
                p["visit_message"] = "First time here!"
                p["visit_status"] = "new"
            else:
                p["visit_message"] = f"Been here {count} time{'s' if count != 1 else ''} before — this will be visit #{next_n}"
                p["visit_status"] = "returning"

            p.update(_duration_stats(p.get("start_date"), p.get("end_date")))
            results.append(p)

    return jsonify(results)


# ---------------------------------------------------------------------------
# Check-in
# ---------------------------------------------------------------------------

@app.route("/api/checkin", methods=["POST"])
def checkin():
    data = request.get_json(force=True)
    iid = data.get("intern_id")
    if not iid:
        return jsonify({"error": "intern_id required"}), 400

    today = today_str()

    with get_db() as conn:
        # Don't double-check-in
        existing = conn.execute(
            """SELECT id FROM checkins
               WHERE intern_id=? AND date(checked_in_at)=? AND checked_out_at IS NULL""",
            (iid, today),
        ).fetchone()
        if existing:
            return jsonify({"error": "Already checked in"}), 409

        now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        cur = conn.execute(
            "INSERT INTO checkins (intern_id, checked_in_at) VALUES (?,?)",
            (iid, now),
        )
        checkin_id = cur.lastrowid

        # Return updated intern data
        row = conn.execute(
            """SELECT i.*, COUNT(c.id) AS visit_count
               FROM interns i
               LEFT JOIN checkins c ON c.intern_id = i.id
               WHERE i.id=?
               GROUP BY i.id""",
            (iid,),
        ).fetchone()

    result = dict(row)
    result["checkin_id"] = checkin_id
    return jsonify(result), 201


# ---------------------------------------------------------------------------
# Check-out
# ---------------------------------------------------------------------------

@app.route("/api/checkout/<int:checkin_id>", methods=["POST"])
def checkout(checkin_id):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        row = conn.execute("SELECT * FROM checkins WHERE id=?", (checkin_id,)).fetchone()
        if not row:
            return jsonify({"error": "Check-in not found"}), 404
        if row["checked_out_at"]:
            return jsonify({"error": "Already checked out"}), 409
        conn.execute(
            "UPDATE checkins SET checked_out_at=? WHERE id=?",
            (now, checkin_id),
        )
    return jsonify({"ok": True, "checked_out_at": now})


@app.route("/api/checkout/all", methods=["POST"])
def checkout_all():
    """Check out every person who is currently here."""
    today = today_str()
    now   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        conn.execute(
            """UPDATE checkins SET checked_out_at=?
               WHERE date(checked_in_at)=? AND checked_out_at IS NULL""",
            (now, today),
        )
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Currently here & left today
# ---------------------------------------------------------------------------

@app.route("/api/here", methods=["GET"])
def here():
    """People currently checked in (no checkout yet today)."""
    _auto_expire()          # always expire before reporting who's here
    today = today_str()
    with get_db() as conn:
        rows = conn.execute(
            """SELECT i.name, i.id AS intern_id, c.id AS checkin_id,
                      c.checked_in_at, i.end_date,
                      (SELECT COUNT(*) FROM checkins c2 WHERE c2.intern_id=i.id) AS visit_count
               FROM checkins c
               JOIN interns i ON i.id = c.intern_id
               WHERE date(c.checked_in_at)=? AND c.checked_out_at IS NULL
               ORDER BY c.checked_in_at""",
            (today,),
        ).fetchall()
    return jsonify([dict(r) for r in rows])


@app.route("/api/left", methods=["GET"])
def left_today():
    """People who checked out today."""
    today = today_str()
    with get_db() as conn:
        rows = conn.execute(
            """SELECT i.name, i.id AS intern_id, c.id AS checkin_id,
                      c.checked_in_at, c.checked_out_at,
                      (SELECT COUNT(*) FROM checkins c2 WHERE c2.intern_id=i.id) AS visit_count
               FROM checkins c
               JOIN interns i ON i.id = c.intern_id
               WHERE date(c.checked_in_at)=? AND c.checked_out_at IS NOT NULL
               ORDER BY c.checked_out_at DESC""",
            (today,),
        ).fetchall()
    return jsonify([dict(r) for r in rows])


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
