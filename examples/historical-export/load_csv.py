"""Load one saved closing-lines CSV into a new SQLite database."""
import argparse
import csv
import os
from pathlib import Path
import re
import sqlite3
import sys
from contextlib import closing
from tempfile import TemporaryDirectory

REQUIRED = {
    "game_date", "sport_key", "home_team", "away_team", "source",
    "player_name", "market_key", "line", "over_price", "under_price", "snapshot_time",
}


def load_export(source: Path, destination: Path) -> int:
    if destination.exists():
        raise FileExistsError(destination)
    with source.open(encoding="utf-8-sig", newline="") as stream:
        rows = csv.reader(stream, strict=True)
        columns = next(rows, [])
        if not REQUIRED.issubset(columns):
            raise ValueError("Missing export columns: " + ", ".join(sorted(REQUIRED - set(columns))))
        if any(not re.fullmatch(r"[A-Za-z_][A-Za-z_0-9]*", name) for name in columns):
            raise ValueError("Expected a plain field name for each CSV column.")
        if len({name.casefold() for name in columns}) != len(columns):
            raise ValueError("The CSV contains duplicate column names.")

        definitions = ", ".join(f'"{name}" TEXT NOT NULL' for name in columns)
        placeholders = ", ".join("?" for _ in columns)
        with TemporaryDirectory(dir=destination.parent) as tmp:
            new_db = Path(tmp) / "snapshot.sqlite"
            new_db.touch(mode=0o600, exist_ok=False)
            with closing(sqlite3.connect(new_db)) as db, db:
                db.execute(f"CREATE TABLE closing_lines ({definitions})")
                insert = f"INSERT INTO closing_lines VALUES ({placeholders})"
                count = 0
                for row in rows:
                    if len(row) != len(columns):
                        raise ValueError(f"Wrong number of fields at CSV line {rows.line_num}.")
                    db.execute(insert, row)
                    count += 1
            # Publish the completed file only if the destination is still free.
            os.link(new_db, destination)
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv", type=Path, help="Existing local closing-lines export")
    parser.add_argument("database", type=Path, help="New SQLite file on a filesystem supporting hard links")
    args = parser.parse_args()
    try:
        count = load_export(args.csv, args.database)
    except FileExistsError:
        print("Choose a new database path. That destination already exists.", file=sys.stderr)
        return 1
    except (OSError, UnicodeError, ValueError, csv.Error, sqlite3.Error) as error:
        print(f"Import failed: {error}", file=sys.stderr)
        return 1
    print(f"Imported {count} rows into {args.database}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
