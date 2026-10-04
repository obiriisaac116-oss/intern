import os
import psycopg2
import psycopg2.extras
from flask import Flask, request, jsonify, render_template
from datetime import datetime, date

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Database connection
# Render injects DATABASE_URL automatically when a Postgres DB is attached.
# For local dev, set DATABASE_URL in your shell or a .env file, e.g.:
#   export DATABASE_URL=postgresql://user:pass@localhost/intern_tracker
# ---------------------------------------------------------------------------

def get_db():
    conn = psycopg2.connect(os.environ["DATABASE_URL"])
    conn.autocommit = False
    return conn


def init_db():
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS interns (
                    id         SERIAL PRIMARY KEY,
                    name       TEXT   NOT NULL UNIQUE,
                    start_date DATE,
                    end_date   DATE,
                    created_at TIMESTAMP NOT NULL DEFAULT NOW()
                );

                CREATE TABLE IF NOT EXISTS checkins (
                    id             SERIAL PRIMARY KEY,
                    intern_id      INTEGER NOT NULL REFERENCES interns(id) ON DELETE CASCADE,
                    checked_in_at  TIMESTAMP NOT NULL DEFAULT NOW(),
                    checked_out_at TIMESTAMP
                );
            """)
        conn.commit()


def today_str():
    return date.today().isoformat()


# ---------------------------------------------------------------------------
# Auto-expire: checkout anyone whose end_date has passed
# ---------------------------------------------------------------------------

def _auto_expire():
    today = today_str()
    now   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE checkins
                SET    checked_out_at = %s
                WHERE  checked_out_at IS NULL
                  AND  intern_id IN (
                           SELECT id FROM interns
                           WHERE  end_date IS NOT NULL AND end_date < %s
                       )
            """, (now, today))
        conn.commit()


# ---------------------------------------------------------------------------
# Duration stats
# ---------------------------------------------------------------------------

def _duration_stats(start_date_val, end_date_val):
    today = date.today()
    stats = {
        "days_elapsed": None, "days_remaining": None,
        "weeks_remaining": None, "months_remaining": None,
        "pct_complete": None, "status": "unknown",
    }

    # Accept both date objects and ISO strings
    def to_date(v):
        if v is None:
            return None
        if isinstance(v, date):
            return v
        try:
            return date.fromisoformat(str(v)[:10])
        except ValueError:
            return None

    start = to_date(start_date_val)
    end   = to_date(end_date_val)

    if not start:
        return stats

    if today < start:
        stats["status"] = "upcoming"
        stats["days_elapsed"] = 0
        if end:
            total = (end - start).days
            stats["days_remaining"]   = total
            stats["weeks_remaining"]  = round(total / 7, 1)
            stats["months_remaining"] = round(total / 30.44, 1)
            stats["pct_complete"]     = 0
        return stats

    stats["days_elapsed"] = (today - start).days

    if end:
        if today > end:
            stats["status"]           = "ended"
            stats["days_remaining"]   = 0
            stats["weeks_remaining"]  = 0
            stats["months_remaining"] = 0
            stats["pct_complete"]     = 100
        else:
            stats["status"]           = "active"
            remaining                 = (end - today).days
            total                     = (end - start).days
            stats["days_remaining"]   = remaining
            stats["weeks_remaining"]  = round(remaining / 7, 1)
            stats["months_remaining"] = round(remaining / 30.44, 1)
            stats["pct_complete"]     = round((stats["days_elapsed"] / max(total, 1)) * 100)
    else:
        stats["status"] = "active"

    return stats


def _row_to_dict(row, cursor):
    """Convert psycopg2 row tuple to dict using cursor description."""
    cols = [d[0] for d in cursor.description]
    d = dict(zip(cols, row))
    # Serialise date/datetime objects to ISO strings
    for k, v in d.items():
        if isinstance(v, (date, datetime)):
            d[k] = v.isoformat()
    return d


# ---------------------------------------------------------------------------
# Initialise on first request (not at import time — DATABASE_URL may not
# be available yet when gunicorn loads the module on Render)
# ---------------------------------------------------------------------------

_db_initialised = False

@app.before_request
def ensure_db():
    global _db_initialised
    if not _db_initialised:
        init_db()
        _db_initialised = True


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
        with conn.cursor() as cur:
            if q:
                cur.execute("""
                    SELECT i.*, COUNT(c.id) AS visit_count
                    FROM   interns i
                    LEFT JOIN checkins c ON c.intern_id = i.id
                    WHERE  LOWER(i.name) LIKE LOWER(%s)
                    GROUP BY i.id ORDER BY i.name
                """, (f"%{q}%",))
            else:
                cur.execute("""
                    SELECT i.*, COUNT(c.id) AS visit_count
                    FROM   interns i
                    LEFT JOIN checkins c ON c.intern_id = i.id
                    GROUP BY i.id ORDER BY i.name
                """)
            rows = cur.fetchall()
            result = []
            for row in rows:
                d = _row_to_dict(row, cur)
                d.update(_duration_stats(d.get("start_date"), d.get("end_date")))
                result.append(d)
    return jsonify(result)


@app.route("/api/interns", methods=["POST"])
def create_intern():
    data       = request.get_json(force=True)
    name       = (data.get("name") or "").strip()
    start_date = (data.get("start_date") or "") or None
    end_date   = (data.get("end_date")   or "") or None
    if not name:
        return jsonify({"error": "name is required"}), 400

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM interns WHERE LOWER(name)=LOWER(%s)", (name,))
            if cur.fetchone():
                return jsonify({"error": f'"{name}" is already registered'}), 409

            cur.execute(
                "INSERT INTO interns (name, start_date, end_date) VALUES (%s,%s,%s) RETURNING id",
                (name, start_date, end_date),
            )
            iid = cur.fetchone()[0]
            cur.execute("""
                SELECT i.*, 0 AS visit_count FROM interns i WHERE id=%s
            """, (iid,))
            row = cur.fetchone()
            d = _row_to_dict(row, cur)
        conn.commit()

    d.update(_duration_stats(d.get("start_date"), d.get("end_date")))
    return jsonify(d), 201


@app.route("/api/interns/<int:iid>", methods=["PUT"])
def update_intern(iid):
    data       = request.get_json(force=True)
    name       = (data.get("name") or "").strip()
    start_date = (data.get("start_date") or "") or None
    end_date   = (data.get("end_date")   or "") or None
    if not name:
        return jsonify({"error": "name is required"}), 400

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE interns SET name=%s, start_date=%s, end_date=%s WHERE id=%s",
                (name, start_date, end_date, iid),
            )
            cur.execute("""
                SELECT i.*, COUNT(c.id) AS visit_count
                FROM   interns i LEFT JOIN checkins c ON c.intern_id=i.id
                WHERE  i.id=%s GROUP BY i.id
            """, (iid,))
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "Not found"}), 404
            d = _row_to_dict(row, cur)
        conn.commit()

    d.update(_duration_stats(d.get("start_date"), d.get("end_date")))
    return jsonify(d)


@app.route("/api/interns/<int:iid>", methods=["DELETE"])
def delete_intern(iid):
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM interns WHERE id=%s", (iid,))
        conn.commit()
    return jsonify({"ok": True})


@app.route("/api/interns/<int:iid>/renew", methods=["POST"])
def renew_intern(iid):
    data       = request.get_json(force=True)
    start_date = (data.get("start_date") or "") or None
    end_date   = (data.get("end_date")   or "") or None
    if not start_date:
        return jsonify({"error": "start_date is required"}), 400

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM interns WHERE id=%s", (iid,))
            if not cur.fetchone():
                return jsonify({"error": "Intern not found"}), 404

            cur.execute(
                "UPDATE interns SET start_date=%s, end_date=%s WHERE id=%s",
                (start_date, end_date, iid),
            )
            cur.execute("""
                SELECT i.*, COUNT(c.id) AS visit_count
                FROM   interns i LEFT JOIN checkins c ON c.intern_id=i.id
                WHERE  i.id=%s GROUP BY i.id
            """, (iid,))
            row = cur.fetchone()
            d = _row_to_dict(row, cur)
        conn.commit()

    d.update(_duration_stats(d.get("start_date"), d.get("end_date")))
    return jsonify(d)


# ---------------------------------------------------------------------------
# Lookup
# ---------------------------------------------------------------------------

@app.route("/api/lookup", methods=["GET"])
def lookup():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])

    today = today_str()

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT i.*, COUNT(c.id) AS visit_count
                FROM   interns i
                LEFT JOIN checkins c ON c.intern_id = i.id
                WHERE  LOWER(i.name) LIKE LOWER(%s)
                GROUP BY i.id ORDER BY i.name LIMIT 8
            """, (f"%{q}%",))
            rows = cur.fetchall()

            results = []
            for row in rows:
                p = _row_to_dict(row, cur)

                cur.execute("""
                    SELECT id FROM checkins
                    WHERE  intern_id=%s
                      AND  DATE(checked_in_at)=%s
                      AND  checked_out_at IS NULL
                """, (p["id"], today))
                active = cur.fetchone()
                p["is_here"]           = active is not None
                p["active_checkin_id"] = active[0] if active else None

                count  = p["visit_count"]
                next_n = count + 1
                if count == 0:
                    p["visit_message"] = "First time here!"
                    p["visit_status"]  = "new"
                else:
                    p["visit_message"] = f"Been here {count} time{'s' if count != 1 else ''} before — this will be visit #{next_n}"
                    p["visit_status"]  = "returning"

                p.update(_duration_stats(p.get("start_date"), p.get("end_date")))
                results.append(p)

    return jsonify(results)


# ---------------------------------------------------------------------------
# Check-in
# ---------------------------------------------------------------------------

@app.route("/api/checkin", methods=["POST"])
def checkin():
    data = request.get_json(force=True)
    iid  = data.get("intern_id")
    if not iid:
        return jsonify({"error": "intern_id required"}), 400

    today = today_str()

    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT id FROM checkins
                WHERE  intern_id=%s AND DATE(checked_in_at)=%s AND checked_out_at IS NULL
            """, (iid, today))
            if cur.fetchone():
                return jsonify({"error": "Already checked in"}), 409

            cur.execute(
                "INSERT INTO checkins (intern_id) VALUES (%s) RETURNING id",
                (iid,),
            )
            checkin_id = cur.fetchone()[0]

            cur.execute("""
                SELECT i.*, COUNT(c.id) AS visit_count
                FROM   interns i
                LEFT JOIN checkins c ON c.intern_id = i.id
                WHERE  i.id=%s GROUP BY i.id
            """, (iid,))
            row = cur.fetchone()
            d   = _row_to_dict(row, cur)
        conn.commit()

    d["checkin_id"] = checkin_id
    return jsonify(d), 201


# ---------------------------------------------------------------------------
# Check-out
# ---------------------------------------------------------------------------

@app.route("/api/checkout/<int:checkin_id>", methods=["POST"])
def checkout(checkin_id):
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT checked_out_at FROM checkins WHERE id=%s", (checkin_id,))
            row = cur.fetchone()
            if not row:
                return jsonify({"error": "Check-in not found"}), 404
            if row[0]:
                return jsonify({"error": "Already checked out"}), 409
            cur.execute(
                "UPDATE checkins SET checked_out_at=%s WHERE id=%s",
                (now, checkin_id),
            )
        conn.commit()
    return jsonify({"ok": True, "checked_out_at": now})


@app.route("/api/checkout/all", methods=["POST"])
def checkout_all():
    today = today_str()
    now   = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                UPDATE checkins SET checked_out_at=%s
                WHERE  DATE(checked_in_at)=%s AND checked_out_at IS NULL
            """, (now, today))
        conn.commit()
    return jsonify({"ok": True})


# ---------------------------------------------------------------------------
# Currently here & left today
# ---------------------------------------------------------------------------

@app.route("/api/here", methods=["GET"])
def here():
    _auto_expire()
    today = today_str()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT i.name, i.id AS intern_id, c.id AS checkin_id,
                       c.checked_in_at, i.end_date,
                       (SELECT COUNT(*) FROM checkins c2 WHERE c2.intern_id=i.id) AS visit_count
                FROM   checkins c
                JOIN   interns i ON i.id = c.intern_id
                WHERE  DATE(c.checked_in_at)=%s AND c.checked_out_at IS NULL
                ORDER BY c.checked_in_at
            """, (today,))
            rows = cur.fetchall()
            result = [_row_to_dict(r, cur) for r in rows]
    return jsonify(result)


@app.route("/api/left", methods=["GET"])
def left_today():
    today = today_str()
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute("""
                SELECT i.name, i.id AS intern_id, c.id AS checkin_id,
                       c.checked_in_at, c.checked_out_at,
                       (SELECT COUNT(*) FROM checkins c2 WHERE c2.intern_id=i.id) AS visit_count
                FROM   checkins c
                JOIN   interns i ON i.id = c.intern_id
                WHERE  DATE(c.checked_in_at)=%s AND c.checked_out_at IS NOT NULL
                ORDER BY c.checked_out_at DESC
            """, (today,))
            rows = cur.fetchall()
            result = [_row_to_dict(r, cur) for r in rows]
    return jsonify(result)


# ---------------------------------------------------------------------------
# Entry point (local dev only — Render uses gunicorn)
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    init_db()
    app.run(debug=True, port=5000)
