"""การเชื่อมต่อฐานข้อมูล SQLite (โหมด WAL) และการอัปเกรดโครงสร้างด้วย Alembic"""
from __future__ import annotations

import logging
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session, sessionmaker

log = logging.getLogger(__name__)
MIGRATIONS = Path(__file__).resolve().parent / "migrations"


def _sqlite_pragmas(dbapi_conn, _record) -> None:  # type: ignore[no-untyped-def]
    cur = dbapi_conn.cursor()
    cur.execute("PRAGMA journal_mode=WAL")
    cur.execute("PRAGMA synchronous=NORMAL")
    cur.execute("PRAGMA foreign_keys=ON")
    cur.execute("PRAGMA busy_timeout=10000")
    cur.close()


def make_engine(db_path: Path) -> Engine:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    eng = create_engine(f"sqlite:///{db_path.as_posix()}", connect_args={"check_same_thread": False},
                        pool_pre_ping=True)
    event.listen(eng, "connect", _sqlite_pragmas)
    return eng


def upgrade(engine: Engine) -> None:
    from alembic import command
    from alembic.config import Config

    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS))
    cfg.attributes["connection"] = None
    with engine.begin() as conn:
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")


class Database:
    def __init__(self, db_path: Path, migrate: bool = True) -> None:
        self.path = db_path
        self.engine = make_engine(db_path)
        if migrate:
            upgrade(self.engine)
        self.Session = sessionmaker(self.engine, expire_on_commit=False)

    @contextmanager
    def session(self) -> Iterator[Session]:
        s = self.Session()
        try:
            yield s
            s.commit()
        except Exception:
            s.rollback()
            raise
        finally:
            s.close()

    def backup_to(self, dst: Path) -> None:
        """สำรองข้อมูลแบบปลอดภัยขณะโปรแกรมทำงาน (sqlite backup API)"""
        import sqlite3

        dst.parent.mkdir(parents=True, exist_ok=True)
        src = sqlite3.connect(str(self.path))
        try:
            out = sqlite3.connect(str(dst))
            with out:
                src.backup(out)
            out.close()
        finally:
            src.close()
