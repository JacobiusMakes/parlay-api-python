import csv
from contextlib import closing
from pathlib import Path
import sqlite3
from tempfile import TemporaryDirectory
import unittest

from load_csv import load_export


class HistoricalImportTest(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.csv = Path(self.tmp.name) / "export.csv"
        self.db = Path(self.tmp.name) / "private.sqlite"
        with Path(__file__).with_name("practice.csv").open(newline="") as f:
            self.rows = list(csv.reader(f))

    def write(self, rows):
        with self.csv.open("w", newline="", encoding="utf-8-sig") as f:
            csv.writer(f).writerows(rows)

    def test_workshop_and_repeat(self):
        self.write(self.rows)
        self.assertEqual(load_export(self.csv, self.db), 3)
        with closing(sqlite3.connect(self.db)) as db:
            result = db.execute(
                "SELECT game_date, source, COUNT(*), SUM(over_price = '' OR under_price = '') "
                "FROM closing_lines GROUP BY game_date, source ORDER BY game_date, source"
            ).fetchall()
        self.assertEqual(result, [
            ("2024-08-16", "practice_book", 2, 1), ("2024-08-17", "practice_book", 1, 0)
        ])
        previous = self.db.read_bytes()
        with self.assertRaises(FileExistsError):
            load_export(self.csv, self.db)
        self.assertEqual(self.db.read_bytes(), previous)

    def test_truncated_record_leaves_no_partial_database(self):
        self.write(self.rows + [self.rows[1][:-1]])
        with self.assertRaisesRegex(ValueError, "Wrong number"):
            load_export(self.csv, self.db)
        self.assertFalse(self.db.exists())
        self.assertEqual(list(self.db.parent.iterdir()), [self.csv])

    def test_empty_export_and_old_headers(self):
        self.write([self.rows[0][:-2]])
        self.assertEqual(load_export(self.csv, self.db), 0)
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute("SELECT COUNT(*) FROM closing_lines").fetchone(), (0,))

    def test_additional_fields_and_quoted_text_survive(self):
        self.rows[0].append("external_id")
        self.rows[1].append("0000042")
        self.rows[1][6] = 'Alex "A", Example'
        self.write(self.rows[:2])
        self.assertEqual(load_export(self.csv, self.db), 1)
        with closing(sqlite3.connect(self.db)) as db:
            self.assertEqual(db.execute("SELECT external_id, player_name FROM closing_lines").fetchone(),
                             ("0000042", 'Alex "A", Example'))

    def test_missing_or_equivalent_headers(self):
        for header in [self.rows[0][1:], self.rows[0] + ["GAME_DATE"]]:
            with self.subTest(header=header):
                self.write([header])
                with self.assertRaises(ValueError):
                    load_export(self.csv, self.db)
                self.assertFalse(self.db.exists())


if __name__ == "__main__":
    unittest.main()
