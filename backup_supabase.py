#!/usr/bin/env python3
"""Create a timestamped Supabase backup with restricted file permissions.

The script reads the database connection only from ``.env`` and never prints
it.  A PostgreSQL custom-format dump is placed inside a ZIP archive.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from dotenv import load_dotenv


PROJECT_ROOT = Path(__file__).resolve().parent
DEFAULT_OUTPUT_DIR = Path("/Users/sangdo/Documents/Backup/Supabase")


def pg_dump_connection_url(database_url: str) -> str:
    """Convert SQLAlchemy's PostgreSQL URL dialect to one pg_dump accepts."""
    parts = urlsplit(database_url)
    scheme = parts.scheme
    if "+" in scheme:
        scheme = scheme.split("+", 1)[0]
    if scheme not in {"postgresql", "postgres"}:
        raise ValueError("DATABASE_URL must use a PostgreSQL connection URL.")
    return urlunsplit((scheme, parts.netloc, parts.path, parts.query, parts.fragment))


def backup_time() -> datetime:
    timezone_name = os.getenv("SUPABASE_BACKUP_TIMEZONE")
    if not timezone_name:
        return datetime.now().astimezone()
    try:
        return datetime.now(ZoneInfo(timezone_name))
    except ZoneInfoNotFoundError as exc:
        raise ValueError(
            "SUPABASE_BACKUP_TIMEZONE must be a valid IANA timezone, "
            "for example Asia/Ho_Chi_Minh."
        ) from exc


def main() -> int:
    load_dotenv(PROJECT_ROOT / ".env")

    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        print("Missing DATABASE_URL in .env.", file=sys.stderr)
        return 2

    try:
        connection_url = pg_dump_connection_url(database_url)
        created_at = backup_time()
        timestamp = created_at.strftime("%Y%m%d_%H%M%S")
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2

    output_dir = Path(
        os.getenv("SUPABASE_BACKUP_OUTPUT_DIR", str(DEFAULT_OUTPUT_DIR))
    ).expanduser()
    output_dir.mkdir(parents=True, exist_ok=True)

    pg_dump = shutil.which("pg_dump")
    if not pg_dump:
        print(
            "pg_dump was not found. Install PostgreSQL client tools and add pg_dump to PATH.",
            file=sys.stderr,
        )
        return 2

    archive_path = output_dir / f"supabase_backup_{timestamp}.zip"
    pending_archive_path = archive_path.with_suffix(".zip.part")

    try:
        with tempfile.TemporaryDirectory(
            prefix="supabase_backup_", dir=output_dir
        ) as temp_dir:
            dump_path = Path(temp_dir) / "database.dump"
            subprocess.run(
                [
                    pg_dump,
                    f"--dbname={connection_url}",
                    "--format=custom",
                    "--no-owner",
                    "--no-privileges",
                    f"--file={dump_path}",
                ],
                check=True,
            )

            if not dump_path.is_file() or dump_path.stat().st_size == 0:
                raise RuntimeError("pg_dump did not create a usable backup file.")

            manifest = (
                "Supabase PostgreSQL backup\n"
                f"Created: {created_at.isoformat()}\n"
                "Format: pg_dump custom archive\n"
                "Restore with: pg_restore --dbname=POSTGRESQL_CONNECTION_URL database.dump\n"
            )
            with zipfile.ZipFile(
                pending_archive_path, mode="w", compression=zipfile.ZIP_DEFLATED
            ) as archive:
                archive.write(dump_path, arcname="database.dump")
                archive.writestr("backup_info.txt", manifest)

        if not zipfile.is_zipfile(pending_archive_path):
            raise RuntimeError("The generated ZIP archive is invalid.")

        pending_archive_path.replace(archive_path)
        archive_path.chmod(0o600)
    except subprocess.CalledProcessError:
        pending_archive_path.unlink(missing_ok=True)
        print(
            "pg_dump failed. Check DATABASE_URL and that its Supabase database is reachable.",
            file=sys.stderr,
        )
        return 1
    except (OSError, RuntimeError, zipfile.BadZipFile) as exc:
        pending_archive_path.unlink(missing_ok=True)
        print(f"Backup failed: {exc}", file=sys.stderr)
        return 1

    print(f"Backup created: {archive_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
