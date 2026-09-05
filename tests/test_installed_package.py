"""Run with the installed wheel's Python, from outside the source checkout.

All network behavior is mocked. The existing starter test suite is replayed
against the installed module so distribution packaging cannot skip validation.
"""

import contextlib
import importlib.metadata
import importlib.util
import io
from pathlib import Path
import runpy
import subprocess
import sys
import unittest
from unittest.mock import patch

import odds_workspace
import parlay_api


ROOT = Path(__file__).resolve().parents[1]


class InstalledPackageTests(unittest.TestCase):
    def test_imports_are_installed_outside_checkout(self):
        for module in (parlay_api, odds_workspace):
            self.assertNotIn(ROOT, Path(module.__file__).resolve().parents)

    def test_version_matches_distribution(self):
        self.assertEqual(parlay_api.__version__, "0.3.3")
        self.assertEqual(importlib.metadata.version("parlay-api"), parlay_api.__version__)

    def test_installed_starter_is_exact_standalone_source(self):
        self.assertEqual(
            Path(odds_workspace.__file__).read_bytes(),
            (ROOT / "examples" / "odds_workspace.py").read_bytes(),
        )

    def test_module_help_works_outside_checkout_without_network(self):
        completed = subprocess.run(
            [sys.executable, "-m", "parlay_api", "--help"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        self.assertEqual(completed.returncode, 0, completed.stderr)
        self.assertIn("usage: python -m parlay_api", completed.stdout)
        self.assertIn("--full", completed.stdout)
        self.assertIn("--no-include-live", completed.stdout)
        self.assertEqual(completed.stderr, "")

    def test_module_delegates_to_existing_starter_and_propagates_exit_code(self):
        with patch.object(odds_workspace, "main", return_value=27) as main:
            with self.assertRaises(SystemExit) as result:
                runpy.run_module("parlay_api", run_name="__main__")
        self.assertEqual(result.exception.code, 27)
        main.assert_called_once_with(prog="python -m parlay_api")

    def test_existing_fixture_and_request_contract_suite_against_installed_module(self):
        spec = importlib.util.spec_from_file_location(
            "installed_workspace_contracts", ROOT / "examples" / "test_odds_workspace.py"
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.starter = odds_workspace
        suite = unittest.defaultTestLoader.loadTestsFromTestCase(module.WorkspaceTests)
        output = io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(output):
            result = unittest.TextTestRunner(stream=output, verbosity=1).run(suite)
        self.assertGreaterEqual(result.testsRun, 24)
        self.assertTrue(result.wasSuccessful(), output.getvalue())


if __name__ == "__main__":
    unittest.main(verbosity=2)
