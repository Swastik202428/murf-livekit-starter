import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path


# ============================================================
# DATABASE CONFIGURATION
# ============================================================

DB_FILE = (
    Path(__file__).resolve().parents[1]
    / "human_help.db"
)


# ============================================================
# TIME
# ============================================================

def _now_iso() -> str:
    """Return current UTC time."""
    return datetime.now(timezone.utc).isoformat()


# ============================================================
# DATABASE INITIALIZATION
# ============================================================

def init_escalation_db() -> sqlite3.Connection:
    """
    Initialize the human-help escalation database.
    """

    DB_FILE.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    conn = sqlite3.connect(
        DB_FILE,
        check_same_thread=False,
    )

    conn.row_factory = sqlite3.Row

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS escalations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            reference_id TEXT UNIQUE NOT NULL,
            caller_id TEXT,
            caller_name TEXT,
            issue_type TEXT NOT NULL,
            summary TEXT NOT NULL,
            agent_checked TEXT NOT NULL,
            urgency TEXT NOT NULL,
            language TEXT,
            preferred_follow_up TEXT,
            status TEXT NOT NULL DEFAULT 'open',
            created_at TEXT NOT NULL
        )
        """
    )

    conn.commit()

    return conn


# ============================================================
# CREATE ESCALATION
# ============================================================

def create_escalation(
    conn: sqlite3.Connection,
    caller_id: str,
    caller_name: str,
    issue_type: str,
    summary: str,
    agent_checked: str,
    urgency: str,
    language: str,
    preferred_follow_up: str,
) -> dict:
    """
    Create a human-help request.

    Only stores the short summary needed by the human reviewer.
    """

    # --------------------------------------------------------
    # Validate urgency
    # --------------------------------------------------------

    allowed_urgencies = {
        "low",
        "medium",
        "high",
        "emergency",
    }

    urgency_clean = (
        urgency.strip().lower()
        if urgency
        else "medium"
    )

    if urgency_clean not in allowed_urgencies:
        urgency_clean = "medium"

    # --------------------------------------------------------
    # Generate reference ID
    # --------------------------------------------------------

    reference_id = (
        "HA-"
        + uuid.uuid4().hex[:8].upper()
    )

    # --------------------------------------------------------
    # Clean values
    # --------------------------------------------------------

    caller_id = (
        caller_id.strip()
        if caller_id
        else ""
    )

    caller_name = (
        caller_name.strip()
        if caller_name
        else "Caller"
    )

    issue_type = (
        issue_type.strip()
        if issue_type
        else "Human assistance"
    )

    summary = (
        summary.strip()
        if summary
        else "No summary provided."
    )

    agent_checked = (
        agent_checked.strip()
        if agent_checked
        else "No additional checks recorded."
    )

    language = (
        language.strip()
        if language
        else "Not specified"
    )

    preferred_follow_up = (
        preferred_follow_up.strip()
        if preferred_follow_up
        else "Not specified"
    )

    # --------------------------------------------------------
    # Insert request
    # --------------------------------------------------------

    conn.execute(
        """
        INSERT INTO escalations (
            reference_id,
            caller_id,
            caller_name,
            issue_type,
            summary,
            agent_checked,
            urgency,
            language,
            preferred_follow_up,
            status,
            created_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            reference_id,
            caller_id,
            caller_name,
            issue_type,
            summary,
            agent_checked,
            urgency_clean,
            language,
            preferred_follow_up,
            "open",
            _now_iso(),
        ),
    )

    conn.commit()

    return {
        "success": True,
        "created": True,
        "reference_id": reference_id,
        "status": "open",
        "urgency": urgency_clean,
        "message": (
            "Human-help request created successfully."
        ),
    }


# ============================================================
# GET OPEN REQUESTS
# ============================================================

def get_open_escalations(
    conn: sqlite3.Connection,
) -> list[dict]:
    """
    Return all currently open human-help requests.
    """

    rows = conn.execute(
        """
        SELECT
            reference_id,
            caller_id,
            caller_name,
            issue_type,
            summary,
            agent_checked,
            urgency,
            language,
            preferred_follow_up,
            status,
            created_at
        FROM escalations
        WHERE status != 'resolved'
        ORDER BY created_at DESC
        """
    ).fetchall()

    return [
        dict(row)
        for row in rows
    ]


# ============================================================
# GET REQUEST BY REFERENCE ID
# ============================================================

def get_escalation(
    conn: sqlite3.Connection,
    reference_id: str,
) -> dict | None:
    """
    Retrieve one human-help request.
    """

    if not reference_id:
        return None

    row = conn.execute(
        """
        SELECT
            reference_id,
            caller_id,
            caller_name,
            issue_type,
            summary,
            agent_checked,
            urgency,
            language,
            preferred_follow_up,
            status,
            created_at
        FROM escalations
        WHERE reference_id = ?
        """,
        (reference_id,),
    ).fetchone()

    if row is None:
        return None

    return dict(row)


# ============================================================
# UPDATE STATUS
# ============================================================

def update_escalation_status(
    conn: sqlite3.Connection,
    reference_id: str,
    status: str,
) -> bool:
    """
    Update human-help request status.
    """

    allowed_statuses = {
        "open",
        "in_progress",
        "resolved",
    }

    if status not in allowed_statuses:
        return False

    cursor = conn.execute(
        """
        UPDATE escalations
        SET status = ?
        WHERE reference_id = ?
        """,
        (
            status,
            reference_id,
        ),
    )

    conn.commit()

    return cursor.rowcount > 0