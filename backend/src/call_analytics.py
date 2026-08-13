import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

logger = logging.getLogger("healthaccess-analytics")


# ============================================================
# DATABASE PATH
# ============================================================

BASE_DIR = Path(__file__).resolve().parent.parent
DB_FILE = BASE_DIR / "call_analytics.db"


# ============================================================
# TIME
# ============================================================

def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ============================================================
# DATABASE CONNECTION
# ============================================================

def _ensure_row_factory(
    conn: sqlite3.Connection,
) -> sqlite3.Connection:
    conn.row_factory = sqlite3.Row
    return conn


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def init_analytics_db(
    conn: sqlite3.Connection | None = None,
) -> sqlite3.Connection:

    # --------------------------------------------------------
    # USE PROVIDED CONNECTION
    # --------------------------------------------------------

    if conn is not None:
        _ensure_row_factory(conn)

        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS calls (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                call_id TEXT UNIQUE NOT NULL,
                timestamp TEXT NOT NULL,
                channel TEXT NOT NULL,
                successful INTEGER NOT NULL DEFAULT 0,
                status TEXT NOT NULL DEFAULT 'active'
            )
            """
        )

        conn.commit()
        return conn

    # --------------------------------------------------------
    # DEDICATED ANALYTICS DATABASE
    # --------------------------------------------------------

    DB_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    conn = sqlite3.connect(
        str(DB_FILE),
        check_same_thread=False,
    )

    _ensure_row_factory(conn)

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS calls (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            call_id TEXT UNIQUE NOT NULL,
            timestamp TEXT NOT NULL,
            channel TEXT NOT NULL,
            successful INTEGER NOT NULL DEFAULT 0,
            status TEXT NOT NULL DEFAULT 'active'
        )
        """
    )

    conn.commit()

    return conn


# ============================================================
# START CALL
# ============================================================

def start_call(
    conn: sqlite3.Connection,
    call_id: str,
    channel: str = "browser",
) -> None:

    if not call_id:
        return

    now = _now_iso()

    existing = conn.execute(
        """
        SELECT id
        FROM calls
        WHERE call_id = ?
        """,
        (call_id,),
    ).fetchone()

    if existing:
        conn.execute(
            """
            UPDATE calls
            SET
                channel = ?,
                timestamp = ?,
                successful = 0,
                status = 'active'
            WHERE call_id = ?
            """,
            (
                channel,
                now,
                call_id,
            ),
        )
        logger.info(
            "DAY 8 ANALYTICS | CALL STARTED | id=%s | channel=%s | status=active | successful=0",
            call_id,
            channel,
        )
    else:
        conn.execute(
            """
            INSERT INTO calls (
                call_id,
                timestamp,
                channel,
                successful,
                status
            )
            VALUES (?, ?, ?, 0, 'active')
            """,
            (
                call_id,
                now,
                channel,
            ),
        )
        logger.info(
            "DAY 8 ANALYTICS | CALL STARTED | id=%s | channel=%s | status=active | successful=0",
            call_id,
            channel,
        )

    conn.commit()


# ============================================================
# FINISH CALL
# ============================================================

def finish_call(
    conn: sqlite3.Connection,
    call_id: str,
    successful: bool = True,
) -> None:

    if not call_id:
        return

    status_value = 1 if successful else 0

    cursor = conn.execute(
        """
        UPDATE calls
        SET
            successful = ?,
            status = 'completed',
            timestamp = COALESCE(timestamp, ?)
        WHERE call_id = ?
        """,
        (
            status_value,
            _now_iso(),
            call_id,
        ),
    )

    if cursor.rowcount == 0:
        conn.execute(
            """
            INSERT INTO calls (
                call_id,
                timestamp,
                channel,
                successful,
                status
            )
            VALUES (?, ?, ?, ?, 'completed')
            """,
            (
                call_id,
                _now_iso(),
                "browser",
                status_value,
            ),
        )

    logger.info(
        "DAY 8 ANALYTICS | CALL FINISHED | id=%s | channel=%s | status=completed | successful=%s",
        call_id,
        conn.execute(
            "SELECT channel FROM calls WHERE call_id = ?",
            (call_id,),
        ).fetchone()[0]
        if conn.execute(
            "SELECT 1 FROM calls WHERE call_id = ?",
            (call_id,),
        ).fetchone()
        else "browser",
        status_value,
    )

    conn.commit()


# ============================================================
# END CALL
# ============================================================

def end_call(
    conn: sqlite3.Connection,
    call_id: str,
    successful: bool = True,
) -> None:

    finish_call(
        conn,
        call_id,
        successful,
    )


# ============================================================
# RECORD COMPLETE CALL
# ============================================================

def record_call(
    conn: sqlite3.Connection,
    channel: str = "browser",
    successful: bool = True,
    call_id: str | None = None,
) -> None:

    if call_id:

        start_call(
            conn,
            call_id,
            channel,
        )

        finish_call(
            conn,
            call_id,
            successful,
        )

        return

    # --------------------------------------------------------
    # GENERATE UNIQUE CALL ID
    # --------------------------------------------------------

    generated_call_id = (
        f"manual-{datetime.now(timezone.utc).timestamp()}"
    )

    start_call(
        conn,
        generated_call_id,
        channel,
    )

    finish_call(
        conn,
        generated_call_id,
        successful,
    )


# ============================================================
# GET STATISTICS
# ============================================================

def get_stats(
    conn: sqlite3.Connection | None = None,
) -> dict[str, int | float]:

    if conn is None:
        conn = init_analytics_db()

    total = conn.execute(
        """
        SELECT COUNT(*)
        FROM calls
        """
    ).fetchone()[0]

    successful = conn.execute(
        """
        SELECT COUNT(*)
        FROM calls
        WHERE successful = 1
        """
    ).fetchone()[0]

    failed = conn.execute(
        """
        SELECT COUNT(*)
        FROM calls
        WHERE successful = 0
        """
    ).fetchone()[0]

    active = conn.execute(
        """
        SELECT COUNT(*)
        FROM calls
        WHERE status = 'active'
        """
    ).fetchone()[0]

    completed = conn.execute(
        """
        SELECT COUNT(*)
        FROM calls
        WHERE status = 'completed'
        """
    ).fetchone()[0]

    browser = conn.execute(
        """
        SELECT COUNT(*)
        FROM calls
        WHERE channel = 'browser'
        """
    ).fetchone()[0]

    sip = conn.execute(
        """
        SELECT COUNT(*)
        FROM calls
        WHERE channel = 'sip'
        """
    ).fetchone()[0]

    total_count = int(total or 0)
    successful_count = int(successful or 0)
    failed_count = int(failed or 0)
    active_count = int(active or 0)
    completed_count = int(completed or 0)
    browser_count = int(browser or 0)
    sip_count = int(sip or 0)

    success_rate = 0.0
    if total_count > 0:
        success_rate = round((successful_count / total_count) * 100, 2)

    logger.info(
        "DAY 8 ANALYTICS | STATS REQUEST | total=%s | successful=%s | failed=%s | active=%s | success_rate=%s",
        total_count,
        successful_count,
        failed_count,
        active_count,
        success_rate,
    )

    return {
        "total": total_count,
        "successful": successful_count,
        "failed": failed_count,
        "active": active_count,
        "completed": completed_count,
        "browser": browser_count,
        "sip": sip_count,
        "success_rate": success_rate,
    }


# ============================================================
# GET RECENT CALLS
# ============================================================

def get_recent_calls(
    conn: sqlite3.Connection,
    limit: int = 20,
) -> list[dict]:

    rows = conn.execute(
        """
        SELECT
            id,
            call_id,
            timestamp,
            channel,
            successful,
            status
        FROM calls
        ORDER BY id DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()

    return [
        {
            "id": row["id"],
            "call_id": row["call_id"],
            "timestamp": row["timestamp"],
            "channel": row["channel"],
            "successful": bool(row["successful"]),
            "status": row["status"],
        }
        for row in rows
    ]


# ============================================================
# GET DASHBOARD DATA
# ============================================================

def get_dashboard_data(
    conn: sqlite3.Connection | None = None,
) -> dict:

    if conn is None:
        conn = init_analytics_db()

    stats = get_stats(conn)

    recent_calls = get_recent_calls(
        conn,
        limit=20,
    )

    return {
        "stats": stats,
        "recent_calls": recent_calls,
    }