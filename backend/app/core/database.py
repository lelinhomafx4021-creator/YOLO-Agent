"""Database helpers.

PostgreSQL is the default backend for the project. SQLite remains as a fallback
for temporary local runs by setting DB_BACKEND=sqlite. Runtime code uses
psycopg-style placeholders; the SQLite cursor wrapper translates them.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
import sqlite3
from typing import Any, Iterator

from sqlmodel import SQLModel, create_engine

from app.core.config import (
    DB_BACKEND,
    PG_DATABASE,
    PG_HOST,
    PG_PASSWORD,
    PG_PORT,
    PG_USER,
    SQLITE_PATH,
    ensure_data_dirs,
)

if DB_BACKEND == "postgres":
    import psycopg2
    import psycopg2.extras

    DATABASE_URL = f"postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DATABASE}"
    engine = create_engine(DATABASE_URL, echo=False)
else:
    DATABASE_URL = f"sqlite:///{Path(SQLITE_PATH).as_posix()}"
    engine = create_engine(DATABASE_URL, echo=False, connect_args={"check_same_thread": False})

_initialized = False


def utc_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def init_db() -> None:
    global _initialized
    if _initialized:
        return
    ensure_data_dirs()
    import app.models  # noqa: F401 - register SQLModel table definitions

    SQLModel.metadata.create_all(engine)
    _run_lightweight_migrations()
    _seed_default_project()
    _cleanup_stuck_runs()
    _initialized = True

def _cleanup_stuck_runs() -> None:
    """把上次意外中断的 running 状态任务标记为 failed。"""
    now = utc_now()
    try:
        if DB_BACKEND == "postgres":
            import psycopg2
            conn = psycopg2.connect(DATABASE_URL)
            try:
                with conn.cursor() as cur:
                    cur.execute("UPDATE training_runs SET status='failed', error='服务器重启导致中断', finished_at=%s WHERE status='running'", (now,))
                    cur.execute("UPDATE training_runs SET status='failed', error='服务器重启导致中断', finished_at=%s WHERE status='created'", (now,))
                    cur.execute("UPDATE evaluation_runs SET status='failed', error='服务器重启导致中断', finished_at=%s WHERE status='running'", (now,))
                conn.commit()
            finally:
                conn.close()
        else:
            conn = sqlite3.connect(SQLITE_PATH)
            try:
                cur = conn.cursor()
                cur.execute("UPDATE training_runs SET status='failed', error='服务器重启导致中断', finished_at=? WHERE status='running'", (now,))
                cur.execute("UPDATE training_runs SET status='failed', error='服务器重启导致中断', finished_at=? WHERE status='created'", (now,))
                cur.execute("UPDATE evaluation_runs SET status='failed', error='服务器重启导致中断', finished_at=? WHERE status='running'", (now,))
                conn.commit()
            finally:
                conn.close()
    except Exception:
        pass


def _run_lightweight_migrations() -> None:
    """Keep existing dev databases compatible without introducing Alembic."""
    if DB_BACKEND == "postgres":
        column_statements = [
            "ALTER TABLE training_runs ADD COLUMN IF NOT EXISTS project_id INTEGER",
            "ALTER TABLE training_runs ADD COLUMN IF NOT EXISTS display_name TEXT DEFAULT ''",
            "ALTER TABLE training_runs ADD COLUMN IF NOT EXISTS dataset_name TEXT DEFAULT ''",
            "ALTER TABLE training_runs ADD COLUMN IF NOT EXISTS report_path TEXT DEFAULT ''",
            "ALTER TABLE training_runs ADD COLUMN IF NOT EXISTS summary TEXT DEFAULT ''",
            "ALTER TABLE training_runs ADD COLUMN IF NOT EXISTS notes TEXT DEFAULT ''",
            "ALTER TABLE training_runs ADD COLUMN IF NOT EXISTS optimizer TEXT DEFAULT 'auto'",
            "ALTER TABLE training_runs ADD COLUMN IF NOT EXISTS lr0 TEXT DEFAULT ''",
            "ALTER TABLE training_runs ADD COLUMN IF NOT EXISTS val_dataset_version_id INTEGER",
            "ALTER TABLE model_versions ADD COLUMN IF NOT EXISTS project_id INTEGER",
            "ALTER TABLE agent_sessions ADD COLUMN IF NOT EXISTS project_id INTEGER",
            "ALTER TABLE iteration_plans ADD COLUMN IF NOT EXISTS project_id INTEGER",
            "ALTER TABLE datasets ADD COLUMN IF NOT EXISTS collection_name TEXT DEFAULT ''",
            "ALTER TABLE dataset_versions ADD COLUMN IF NOT EXISTS dtype TEXT DEFAULT ''",
            "ALTER TABLE dataset_versions ADD COLUMN IF NOT EXISTS missing_labels INTEGER DEFAULT 0",
            "ALTER TABLE dataset_versions ADD COLUMN IF NOT EXISTS orphan_labels INTEGER DEFAULT 0",
            "ALTER TABLE dataset_versions ADD COLUMN IF NOT EXISTS invalid_bboxes INTEGER DEFAULT 0",
            "ALTER TABLE dataset_versions ADD COLUMN IF NOT EXISTS empty_labels INTEGER DEFAULT 0",
            "ALTER TABLE dataset_versions ADD COLUMN IF NOT EXISTS class_distribution_json TEXT DEFAULT '{}'",
            "ALTER TABLE dataset_versions ADD COLUMN IF NOT EXISTS suggestions_json TEXT DEFAULT '[]'",
            "ALTER TABLE dataset_versions ADD COLUMN IF NOT EXISTS audit_report_path TEXT DEFAULT ''",
            "ALTER TABLE evaluation_runs ADD COLUMN IF NOT EXISTS report_path TEXT DEFAULT ''",
            "ALTER TABLE evaluation_runs ADD COLUMN IF NOT EXISTS summary TEXT DEFAULT ''",
            "ALTER TABLE model_versions ADD COLUMN IF NOT EXISTS model_name TEXT DEFAULT ''",
            "ALTER TABLE model_versions ADD COLUMN IF NOT EXISTS notes TEXT DEFAULT ''",
            "ALTER TABLE model_versions ADD COLUMN IF NOT EXISTS model_format TEXT DEFAULT ''",
            "ALTER TABLE projects ADD COLUMN IF NOT EXISTS workspace_name TEXT DEFAULT ''",
            "ALTER TABLE iteration_plans ADD COLUMN IF NOT EXISTS is_read INTEGER DEFAULT 0",
            """
            CREATE TABLE IF NOT EXISTS dataset_exports (
                id SERIAL PRIMARY KEY,
                dataset_version_id INTEGER NOT NULL,
                export_name TEXT NOT NULL,
                export_path TEXT NOT NULL,
                train_count INTEGER NOT NULL DEFAULT 0,
                val_count INTEGER NOT NULL DEFAULT 0,
                test_count INTEGER NOT NULL DEFAULT 0,
                train_ratio DOUBLE PRECISION NOT NULL DEFAULT 0.7,
                val_ratio DOUBLE PRECISION NOT NULL DEFAULT 0.2,
                test_ratio DOUBLE PRECISION NOT NULL DEFAULT 0.1,
                created_at TEXT NOT NULL
            )
            """,
        ]
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_image_items_version ON image_items(dataset_version_id)",
            "CREATE INDEX IF NOT EXISTS idx_training_runs_project ON training_runs(project_id)",
            "CREATE INDEX IF NOT EXISTS idx_model_versions_project ON model_versions(project_id)",
            "CREATE INDEX IF NOT EXISTS idx_model_versions_run ON model_versions(training_run_id)",
            "CREATE INDEX IF NOT EXISTS idx_training_metrics_run ON training_metrics(training_run_id)",
            "CREATE INDEX IF NOT EXISTS idx_eval_runs_project ON evaluation_runs(project_id)",
            "CREATE INDEX IF NOT EXISTS idx_bindings_project ON project_dataset_bindings(project_id, is_active)",
            "CREATE INDEX IF NOT EXISTS idx_image_status ON image_items(annotation_status)",
        ]
        conn = psycopg2.connect(DATABASE_URL)
        try:
            with conn.cursor() as cur:
                for statement in column_statements:
                    cur.execute(statement)
                for index_sql in indexes:
                    cur.execute(index_sql)
            conn.commit()
        finally:
            conn.close()
        return

    conn = sqlite3.connect(SQLITE_PATH)
    try:
        cur = conn.cursor()
        migrations = {
            "datasets": [
                ("collection_name", "TEXT DEFAULT ''"),
            ],
            "training_runs": [
                ("project_id", "INTEGER"),
                ("display_name", "TEXT DEFAULT ''"),
                ("dataset_name", "TEXT DEFAULT ''"),
                ("report_path", "TEXT DEFAULT ''"),
                ("summary", "TEXT DEFAULT ''"),
                ("notes", "TEXT DEFAULT ''"),
                ("optimizer", "TEXT DEFAULT 'auto'"),
                ("lr0", "TEXT DEFAULT ''"),
                ("val_dataset_version_id", "INTEGER"),
            ],
            "model_versions": [("project_id", "INTEGER"), ("model_format", "TEXT DEFAULT ''")],
            "agent_sessions": [("project_id", "INTEGER")],
            "iteration_plans": [("project_id", "INTEGER"), ("is_read", "INTEGER DEFAULT 0")],
            "evaluation_runs": [
                ("report_path", "TEXT DEFAULT ''"),
                ("summary", "TEXT DEFAULT ''"),
            ],
            "dataset_versions": [
                ("dtype", "TEXT DEFAULT ''"),
                ("missing_labels", "INTEGER DEFAULT 0"),
                ("orphan_labels", "INTEGER DEFAULT 0"),
                ("invalid_bboxes", "INTEGER DEFAULT 0"),
                ("empty_labels", "INTEGER DEFAULT 0"),
                ("class_distribution_json", "TEXT DEFAULT '{}'"),
                ("suggestions_json", "TEXT DEFAULT '[]'"),
                ("audit_report_path", "TEXT DEFAULT ''"),
            ],
        }
        for table, columns in migrations.items():
            existing = {row[1] for row in cur.execute(f"PRAGMA table_info({table})").fetchall()}
            for name, definition in columns:
                if name not in existing:
                    cur.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")
        conn.commit()

        # 从数据集名称自动推断合集名（只去掉末尾的 _train/_val/_test/_inference）
        try:
            import re
            rows = cur.execute("SELECT id, name FROM datasets WHERE collection_name = '' OR collection_name IS NULL").fetchall()
            for row in rows:
                ds_id, ds_name = row[0], row[1]
                coll = re.sub(r'_(train|val|test|inference)$', '', ds_name)
                cur.execute("UPDATE datasets SET collection_name = ? WHERE id = ?", (coll, ds_id))
            conn.commit()
        except Exception:
            pass

        conn.commit()

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS dataset_exports (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                dataset_version_id INTEGER NOT NULL,
                export_name TEXT NOT NULL,
                export_path TEXT NOT NULL,
                train_count INTEGER NOT NULL DEFAULT 0,
                val_count INTEGER NOT NULL DEFAULT 0,
                test_count INTEGER NOT NULL DEFAULT 0,
                train_ratio REAL NOT NULL DEFAULT 0.7,
                val_ratio REAL NOT NULL DEFAULT 0.2,
                test_ratio REAL NOT NULL DEFAULT 0.1,
                created_at TEXT NOT NULL
            )
            """
        )
        # 性能索引
        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_image_items_version ON image_items(dataset_version_id)",
            "CREATE INDEX IF NOT EXISTS idx_training_runs_project ON training_runs(project_id)",
            "CREATE INDEX IF NOT EXISTS idx_model_versions_project ON model_versions(project_id)",
            "CREATE INDEX IF NOT EXISTS idx_model_versions_run ON model_versions(training_run_id)",
            "CREATE INDEX IF NOT EXISTS idx_training_metrics_run ON training_metrics(training_run_id)",
            "CREATE INDEX IF NOT EXISTS idx_eval_runs_project ON evaluation_runs(project_id)",
            "CREATE INDEX IF NOT EXISTS idx_bindings_project ON project_dataset_bindings(project_id, is_active)",
            "CREATE INDEX IF NOT EXISTS idx_image_status ON image_items(annotation_status)",
        ]
        for sql in indexes:
            cur.execute(sql)
        conn.commit()
    finally:
        conn.close()


def _seed_default_project() -> None:
    """Create a default project and attach legacy records to it."""
    now = utc_now()
    if DB_BACKEND == "postgres":
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        placeholder = "%s"
    else:
        conn = sqlite3.connect(SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        placeholder = "?"
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM projects ORDER BY id ASC LIMIT 1")
        project = cur.fetchone()
        if project is None:
            cur.execute(
                f"""
                INSERT INTO projects(name, description, task_type, status, created_at, updated_at)
                VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
                """,
                ("默认项目", "系统自动创建，用于承接历史训练和模型记录。", "detect", "active", now, now),
            )
            cur.execute("SELECT * FROM projects ORDER BY id ASC LIMIT 1")
            project = cur.fetchone()

        project_id = project["id"] if isinstance(project, dict) else project[0]
        for table in ("training_runs", "model_versions", "agent_sessions", "iteration_plans"):
            cur.execute(f"UPDATE {table} SET project_id = {placeholder} WHERE project_id IS NULL", (project_id,))
        conn.commit()
    finally:
        conn.close()


class SQLiteCursor:
    def __init__(self, cursor: sqlite3.Cursor):
        self.cursor = cursor

    def execute(self, query: str, params: tuple = ()) -> "SQLiteCursor":
        self.cursor.execute(query.replace("%s", "?"), params)
        return self

    def fetchone(self) -> sqlite3.Row | None:
        return self.cursor.fetchone()

    def fetchall(self) -> list[sqlite3.Row]:
        return self.cursor.fetchall()

    def close(self) -> None:
        self.cursor.close()


class PostgresCursor:
    """Wrapper so psycopg2 cursor.execute() returns self (supports chaining)."""
    def __init__(self, cursor: Any):
        self.cursor = cursor
    def execute(self, query: str, params: tuple = ()) -> "PostgresCursor":
        self.cursor.execute(query, params)
        return self
    def fetchone(self) -> Any:
        return self.cursor.fetchone()
    def fetchall(self) -> list[Any]:
        return self.cursor.fetchall()
    def close(self) -> None:
        self.cursor.close()


@contextmanager
def db() -> Iterator[Any]:
    """Yield a dict-friendly cursor and commit or roll back automatically."""
    init_db()
    if DB_BACKEND == "postgres":
        conn = psycopg2.connect(DATABASE_URL, cursor_factory=psycopg2.extras.RealDictCursor)
        cur = PostgresCursor(conn.cursor())
    else:
        conn = sqlite3.connect(SQLITE_PATH, timeout=60)
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA busy_timeout=60000")
        conn.row_factory = sqlite3.Row
        cur = SQLiteCursor(conn.cursor())
    try:
        yield cur
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()


def dict_from_row(row: Any) -> dict[str, Any] | None:
    return dict(row) if row else None


def fetch_one(query: str, params: tuple = ()) -> dict[str, Any] | None:
    with db() as cur:
        cur.execute(query, params)
        return dict_from_row(cur.fetchone())


def fetch_all(query: str, params: tuple = ()) -> list[dict[str, Any]]:
    with db() as cur:
        cur.execute(query, params)
        return [dict(r) for r in cur.fetchall() if r is not None]


def as_path(value: str | Path) -> Path:
    return Path(value).expanduser().resolve()
