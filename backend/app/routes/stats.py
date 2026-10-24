"""Dashboard statistics. `tz` is the browser's time zone (e.g. 'Asia/Kolkata') so that
"today" and "this month" match the user's clock, not the server's."""
from fastapi import APIRouter, Depends, HTTPException, Query

from ..auth import current_user
from ..db import get_conn

router = APIRouter(prefix="/stats", tags=["stats"])


def check_tz(conn, tz: str) -> str:
    if not conn.execute("SELECT 1 FROM pg_timezone_names WHERE name = %s", (tz,)).fetchone():
        raise HTTPException(400, f"Unknown time zone '{tz}'")
    return tz


@router.get("/overview")
def overview(tz: str = Query("UTC"), user=Depends(current_user), conn=Depends(get_conn)):
    tz = check_tz(conn, tz)
    p = {"uid": user["id"], "tz": tz}

    totals = conn.execute(
        """
        SELECT
          (SELECT count(*) FROM v_paper_role WHERE user_id = %(uid)s)                    AS papers,
          (SELECT count(*) FROM v_paper_role r
             LEFT JOIN paper_reading_state s ON s.paper_id = r.paper_id AND s.user_id = r.user_id
            WHERE r.user_id = %(uid)s AND coalesce(s.status, 'to_read') = 'to_read')     AS to_read,
          (SELECT count(*) FROM paper_reading_state WHERE user_id = %(uid)s AND status = 'reading') AS reading,
          (SELECT count(*) FROM paper_reading_state WHERE user_id = %(uid)s AND status = 'done')    AS done,
          (SELECT count(*) FROM highlights WHERE user_id = %(uid)s)                      AS highlights,
          (SELECT count(*) FROM notes WHERE user_id = %(uid)s)                           AS notes,
          (SELECT count(*) FROM concepts WHERE owner_id = %(uid)s)                       AS concepts,
          (SELECT coalesce(sum(extract(epoch FROM ended_at - started_at)), 0)::int
             FROM reading_sessions WHERE user_id = %(uid)s)                              AS seconds_read
        """,
        p,
    ).fetchone()

    # Papers finished per month for the last 12 months, plus a running total (window function).
    finished_by_month = conn.execute(
        """
        WITH months AS (
            SELECT generate_series(
                       date_trunc('month', now() AT TIME ZONE %(tz)s) - interval '11 months',
                       date_trunc('month', now() AT TIME ZONE %(tz)s),
                       interval '1 month')::date AS month
        ), finished AS (
            SELECT date_trunc('month', finished_at AT TIME ZONE %(tz)s)::date AS month, count(*) AS n
            FROM paper_reading_state
            WHERE user_id = %(uid)s AND finished_at IS NOT NULL
            GROUP BY 1
        )
        SELECT to_char(m.month, 'Mon YY') AS label,
               coalesce(f.n, 0) AS finished,
               sum(coalesce(f.n, 0)) OVER (ORDER BY m.month) AS running_total
        FROM months m LEFT JOIN finished f USING (month)
        ORDER BY m.month
        """,
        p,
    ).fetchall()

    # Minutes read per day over the last 30 days (days with no reading show as 0).
    daily_minutes = conn.execute(
        """
        SELECT to_char(d.day, 'DD Mon') AS label, round(coalesce(a.seconds, 0) / 60.0)::int AS minutes
        FROM generate_series((now() AT TIME ZONE %(tz)s)::date - 29,
                             (now() AT TIME ZONE %(tz)s)::date, interval '1 day') AS d(day)
        LEFT JOIN activity_days(%(uid)s, %(tz)s) a ON a.day = d.day::date
        ORDER BY d.day
        """,
        p,
    ).fetchall()

    tags = conn.execute(
        "SELECT tag, n FROM v_tag_counts WHERE user_id = %(uid)s ORDER BY n DESC", p
    ).fetchall()

    # RANK() gives ties the same position (two papers cited 3 times are both #1).
    most_cited = conn.execute(
        """
        SELECT * FROM (
            SELECT p.id, p.title, count(c.citing_paper_id) AS cited_by,
                   rank() OVER (ORDER BY count(c.citing_paper_id) DESC) AS rank
            FROM papers p
            JOIN v_paper_role r ON r.paper_id = p.id AND r.user_id = %(uid)s
            JOIN citations c ON c.cited_paper_id = p.id
            GROUP BY p.id
        ) ranked WHERE rank <= 5 ORDER BY rank, title
        """,
        p,
    ).fetchall()

    most_highlighted = conn.execute(
        """
        SELECT p.id, p.title, count(*) AS highlights,
               round(100.0 * count(*) / sum(count(*)) OVER (), 1) AS pct_of_all
        FROM highlights h JOIN papers p ON p.id = h.paper_id
        WHERE h.user_id = %(uid)s
        GROUP BY p.id
        ORDER BY count(*) DESC
        LIMIT 5
        """,
        p,
    ).fetchall()

    return {
        "totals": totals,
        "finished_by_month": finished_by_month,
        "daily_minutes": daily_minutes,
        "tags": tags,
        "most_cited": most_cited,
        "most_highlighted": most_highlighted,
    }


@router.get("/streak")
def streak(tz: str = Query("UTC"), user=Depends(current_user), conn=Depends(get_conn)):
    """Current and longest streak of consecutive active days: the "gaps and islands" trick.

    For consecutive days, (day - row_number) is the same constant, e.g.
        Mar 3 - 1 = Mar 2,  Mar 4 - 2 = Mar 2,  Mar 5 - 3 = Mar 2   -> one island
        Mar 9 - 4 = Mar 5                                          -> a new island
    so grouping by that value gives one row per unbroken run of days.
    """
    tz = check_tz(conn, tz)
    row = conn.execute(
        """
        WITH days AS (
            SELECT day FROM activity_days(%(uid)s, %(tz)s)
        ), grouped AS (
            SELECT day, day - (row_number() OVER (ORDER BY day))::int AS island
            FROM days
        ), islands AS (
            SELECT min(day) AS first_day, max(day) AS last_day, count(*) AS length
            FROM grouped GROUP BY island
        )
        SELECT
            coalesce(max(length), 0) AS longest,
            -- the current streak is the island that ends today or yesterday (still alive)
            coalesce(max(length) FILTER (
                WHERE last_day >= (now() AT TIME ZONE %(tz)s)::date - 1), 0) AS current,
            bool_or(last_day = (now() AT TIME ZONE %(tz)s)::date) AS active_today,
            (SELECT count(*) FROM days) AS total_active_days
        FROM islands
        """,
        {"uid": user["id"], "tz": tz},
    ).fetchone()
    row["active_today"] = bool(row["active_today"])
    return row


@router.get("/calendar")
def calendar(tz: str = Query("UTC"), user=Depends(current_user), conn=Depends(get_conn)):
    """Activity for each of the last 371 days (53 weeks), for the GitHub-style heatmap."""
    tz = check_tz(conn, tz)
    return conn.execute(
        """
        SELECT d.day::date AS day,
               coalesce(a.seconds, 0)    AS seconds,
               coalesce(a.highlights, 0) AS highlights
        FROM generate_series((now() AT TIME ZONE %(tz)s)::date - 370,
                             (now() AT TIME ZONE %(tz)s)::date, interval '1 day') AS d(day)
        LEFT JOIN activity_days(%(uid)s, %(tz)s) a ON a.day = d.day::date
        ORDER BY d.day
        """,
        {"uid": user["id"], "tz": tz},
    ).fetchall()
