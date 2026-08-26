"""Database layer shared by the web GUI and the CLI.

Uses a single Postgres `applications` table modeled on the tracking
spreadsheet. Connection info comes from the DATABASE_URL env var.
"""

import os

from dotenv import load_dotenv

# Load DATABASE_URL from a local .env file (not committed to git).
load_dotenv()

import psycopg2
import psycopg2.extras

# Default to a local database named "jobtracker" if none is configured.
DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://localhost/jobtracker")

# Allowed dropdown values, reused by both the web form and the CLI.
LOCATION_TYPES = ["onsite", "hybrid", "remote"]
STATUSES = ["applied", "interview", "rejected", "offer"]


def get_connection():
    """Open a new Postgres connection using DATABASE_URL."""
    return psycopg2.connect(DATABASE_URL)


def init_db():
    """Create the applications table if it does not already exist."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS applications (
                id              SERIAL PRIMARY KEY,
                role            TEXT,
                company         TEXT,
                location        TEXT,
                location_type   TEXT,
                pay             TEXT,
                app_date        DATE,
                due_date        DATE,
                job_id          TEXT,
                link            TEXT,
                energy_related  BOOLEAN DEFAULT FALSE,
                status          TEXT DEFAULT 'applied',
                job_description TEXT,
                jd_source       TEXT,
                created_at      TIMESTAMPTZ DEFAULT now()
            )
            """
        )


def add_application(data):
    """Insert one application row.

    `data` is a dict whose keys match the column names. Missing keys are
    stored as NULL. Returns the new row id.
    """
    fields = [
        "role", "company", "location", "location_type", "pay",
        "app_date", "due_date", "job_id", "link", "energy_related",
        "status", "job_description", "jd_source",
    ]
    values = [data.get(f) for f in fields]
    placeholders = ", ".join(["%s"] * len(fields))
    columns = ", ".join(fields)
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            f"INSERT INTO applications ({columns}) VALUES ({placeholders}) RETURNING id",
            values,
        )
        return cur.fetchone()[0]


def list_applications():
    """Return all applications as dict-like rows, newest first."""
    with get_connection() as conn, conn.cursor(
        cursor_factory=psycopg2.extras.RealDictCursor
    ) as cur:
        cur.execute("SELECT * FROM applications ORDER BY app_date DESC NULLS LAST, id DESC")
        return cur.fetchall()


def get_application(app_id):
    """Return a single application by id, or None if not found."""
    with get_connection() as conn, conn.cursor(
        cursor_factory=psycopg2.extras.RealDictCursor
    ) as cur:
        cur.execute("SELECT * FROM applications WHERE id = %s", (app_id,))
        return cur.fetchone()


def update_jd(app_id, job_description, jd_source):
    """Store captured job description text and its source for an application."""
    with get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "UPDATE applications SET job_description = %s, jd_source = %s WHERE id = %s",
            (job_description, jd_source, app_id),
        )
