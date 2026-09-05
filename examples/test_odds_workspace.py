"""Offline tests: source capture replay and mocked HTTP, with no real API requests."""

import ast
import contextlib
import copy
import csv
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import unittest
from unittest.mock import Mock, patch
from urllib.error import HTTPError, URLError
from urllib.parse import parse_qs, urlparse


HERE = Path(__file__).resolve().parent
SPEC = importlib.util.spec_from_file_location("odds_workspace", HERE / "odds_workspace.py")
starter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(starter)
CAPTURE_PATH = HERE / "fixtures" / "odds-demo-2026-09-05.json"
CAPTURE = json.loads(CAPTURE_PATH.read_text())


class FakeResponse:
    status = 200

    def __init__(self, body):
        self.body = body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self, limit):
        return self.body[:limit]


class WorkspaceTests(unittest.TestCase):
    def run_cli(self, argv=(), body=None, error=None, environ=None):
        if body is None:
            body = json.dumps(CAPTURE).encode()
        opener = Mock()
        if error:
            opener.open.side_effect = error
        else:
            opener.open.return_value = FakeResponse(body)
        stdout, stderr = io.StringIO(), io.StringIO()
        with (
            patch.object(starter, "build_opener", return_value=opener),
            patch.dict(os.environ, environ or {}, clear=True),
            contextlib.redirect_stdout(stdout),
            contextlib.redirect_stderr(stderr),
        ):
            code = starter.main(list(argv))
        return code, stdout.getvalue(), stderr.getvalue(), opener

    def test_capture_integrity_and_ambiguity(self):
        provenance = json.loads(CAPTURE_PATH.with_suffix(".provenance.json").read_text())
        self.assertFalse(provenance["authenticated"])
        self.assertEqual(
            hashlib.sha256(CAPTURE_PATH.read_bytes()).hexdigest(), provenance["subset_sha256"]
        )
        before = copy.deepcopy(CAPTURE)
        rows, issues = starter.inspect_sample(CAPTURE)
        self.assertEqual(CAPTURE, before)
        self.assertEqual(len(rows), 2)
        self.assertEqual([row["bookmaker_key"] for row in rows], ["novig", "novig"])
        self.assertEqual([row["price"] for row in rows], [135, -138])
        self.assertEqual(rows[0]["bookmaker_last_update"], "2026-09-05T03:58:00Z")
        self.assertEqual(rows[0]["market_last_update"], "2026-09-05T03:54:06Z")
        self.assertEqual([issue["code"] for issue in issues], ["duplicate_market"])

    def test_demo_does_not_read_key_and_makes_one_request(self):
        original_get = os.environ.get

        def guarded_get(name, *args):
            if name == "PARLAY_API_KEY":
                raise AssertionError("Demo attempted to read the API key")
            return original_get(name, *args)

        with patch.object(starter.os.environ, "get", side_effect=guarded_get):
            code, stdout, stderr, opener = self.run_cli()
        self.assertEqual(code, 0)
        opener.open.assert_called_once()
        request = opener.open.call_args.args[0]
        self.assertEqual(request.full_url, "https://parlay-api.com/v1/try/baseball_mlb/odds")
        self.assertIsNone(request.get_header("X-api-key"))
        self.assertEqual(request.get_header("User-agent"), "ParlayAPI-odds-workspace/1.0")
        self.assertEqual(opener.open.call_args.kwargs["timeout"], 30)
        self.assertEqual(len(list(csv.DictReader(io.StringIO(stdout)))), 2)
        self.assertIn("first five US moneyline", stderr)
        self.assertIn("1 validation issues", stderr)

    def test_existing_environment_key_is_ignored_without_full(self):
        _, stdout, stderr, opener = self.run_cli(environ={"PARLAY_API_KEY": "offline-placeholder"})
        self.assertIsNone(opener.open.call_args.args[0].get_header("X-api-key"))
        self.assertNotIn("offline-placeholder", stdout + stderr)

    def test_full_requires_key_before_any_network_call(self):
        code, stdout, stderr, opener = self.run_cli(["--full"])
        self.assertEqual(code, 2)
        self.assertEqual(stdout, "")
        self.assertIn("Set PARLAY_API_KEY", stderr)
        opener.open.assert_not_called()

    def test_full_has_explicit_region_format_live_and_market_parameters(self):
        code, stdout, stderr, opener = self.run_cli(
            ["--full", "--sport", "soccer_epl", "--markets", "totals,h2h,totals"],
            body=b"[]",
            environ={"PARLAY_API_KEY": "offline-placeholder"},
        )
        self.assertEqual(code, 0)
        opener.open.assert_called_once()
        request = opener.open.call_args.args[0]
        parsed = urlparse(request.full_url)
        self.assertEqual(parsed.netloc, "parlay-api.com")
        self.assertEqual(parsed.path, "/v1/sports/soccer_epl/odds")
        self.assertEqual(
            parse_qs(parsed.query),
            {
                "regions": ["us"],
                "markets": ["h2h,totals"],
                "oddsFormat": ["american"],
                "dateFormat": ["iso"],
                "include_live": ["true"],
            },
        )
        self.assertEqual(request.get_header("X-api-key"), "offline-placeholder")
        self.assertEqual(request.get_header("User-agent"), "ParlayAPI-odds-workspace/1.0")
        self.assertNotIn("offline-placeholder", stdout + stderr + request.full_url)
        args = starter.parse_args(["--full", "--no-include-live"])
        self.assertEqual(
            parse_qs(urlparse(starter.request_url(args)).query)["include_live"], ["false"]
        )

    def test_demo_rejects_unsupported_filters_and_unknown_sports_before_network(self):
        for argv in (
            ["--markets", "spreads"],
            ["--include-live"],
            ["--no-include-live"],
            ["--sport", "unknown"],
            ["--markets", "props"],
            ["--regions", "eu"],
        ):
            with self.subTest(argv=argv), patch.object(starter, "build_opener") as opener:
                with (
                    contextlib.redirect_stderr(io.StringIO()),
                    self.assertRaises(SystemExit) as error,
                ):
                    starter.main(argv)
                self.assertEqual(error.exception.code, 2)
                opener.assert_not_called()

    def test_all_six_sports_are_keyless_and_single_request(self):
        for sport in starter.SPORTS:
            code, _, _, opener = self.run_cli(["--sport", sport], body=b'{"demo":true,"events":[]}')
            self.assertEqual(code, 0)
            opener.open.assert_called_once()
            self.assertEqual(opener.open.call_args.args[0].full_url.split("/")[-2], sport)

    def test_equal_market_duplicates_are_also_excluded(self):
        data = copy.deepcopy(CAPTURE)
        book = data["events"][0]["bookmakers"][1]
        book["markets"].append(copy.deepcopy(book["markets"][0]))
        rows, issues = starter.inspect_sample(data)
        self.assertEqual(rows, [])
        self.assertEqual([issue["code"] for issue in issues], ["duplicate_market"] * 2)

    def test_duplicate_book_or_event_identity_is_not_double_counted(self):
        for level in ("book", "event", "canonical_event"):
            data = copy.deepcopy(CAPTURE)
            if level == "book":
                data["events"][0]["bookmakers"].append(
                    copy.deepcopy(data["events"][0]["bookmakers"][1])
                )
            else:
                duplicate = copy.deepcopy(data["events"][0])
                if level == "canonical_event":
                    duplicate["id"] = "test-other-source-id"
                data["events"].append(duplicate)
            rows, issues = starter.inspect_sample(data)
            self.assertEqual(rows, [], level)
            self.assertTrue(issues)

    def test_malformed_prices_and_outcome_identity_exclude_whole_market(self):
        for value in ("135", True, None, float("nan"), float("inf"), 1.35):
            data = copy.deepcopy(CAPTURE)
            data["events"][0]["bookmakers"][1]["markets"][0]["outcomes"][0]["price"] = value
            self.assertEqual(starter.inspect_sample(data)[0], [])
        data = copy.deepcopy(CAPTURE)
        outcomes = data["events"][0]["bookmakers"][1]["markets"][0]["outcomes"]
        outcomes[1]["name"] = outcomes[0]["name"]
        self.assertEqual(starter.inspect_sample(data)[0], [])

    def test_missing_or_invalid_timestamps_are_never_filled(self):
        data = copy.deepcopy(CAPTURE)
        event = data["events"][0]
        event["commence_time"] = None
        book = event["bookmakers"][1]
        book["last_update"] = "2026-02-30T03:58:00Z"
        del book["markets"][0]["last_update"]
        rows, issues = starter.inspect_sample(data)
        self.assertIsNone(rows[0]["commence_time"])
        self.assertIsNone(rows[0]["bookmaker_last_update"])
        self.assertIsNone(rows[0]["market_last_update"])
        self.assertIn("invalid_timestamp", [issue["code"] for issue in issues])

    def test_csv_formula_escaping_preserves_numeric_prices(self):
        rows, _ = starter.inspect_sample(CAPTURE)
        rows[0]["bookmaker_title"] = ' =HYPERLINK("example")'
        rows[1]["outcome_name"] = "\t@SUM(A1)"
        exported = list(csv.DictReader(io.StringIO(starter.to_csv(rows))))
        self.assertEqual(exported[0]["bookmaker_title"], '\' =HYPERLINK("example")')
        self.assertEqual(exported[1]["outcome_name"], "'\t@SUM(A1)")
        self.assertEqual(exported[1]["price"], "-138")

    def test_empty_success_is_csv_header_and_explicit_diagnostic(self):
        for args, body in (([], b'{"demo":true,"events":[]}'), (["--full"], b"[]")):
            code, stdout, stderr, _ = self.run_cli(
                args, body=body, environ={"PARLAY_API_KEY": "offline-placeholder"}
            )
            self.assertEqual(code, 0)
            self.assertEqual(stdout, ",".join(starter.CSV_FIELDS) + "\r\n")
            self.assertIn("does not establish coverage", stderr)

    def test_http_errors_do_not_retry_or_print_server_body(self):
        for status in (302, 401, 403, 429, 500):
            error = HTTPError(
                "https://parlay-api.com/test",
                status,
                "untrusted text",
                {"Retry-After": "30"},
                io.BytesIO(b"untrusted server body"),
            )
            code, stdout, stderr, opener = self.run_cli(error=error)
            self.assertEqual(code, 1)
            self.assertEqual(stdout, "")
            self.assertIn("HTTP " + str(status), stderr)
            self.assertNotIn("untrusted text", stderr)
            self.assertNotIn("Check your key", stderr)
            self.assertEqual("Retry-After: 30" in stderr, status == 429)
            opener.open.assert_called_once()
            self.assertTrue(error.closed)

    def test_demo_and_full_403_diagnostics_distinguish_authentication(self):
        for args in ([], ["--full"]):
            error = HTTPError(
                "https://parlay-api.com/test", 403, "forbidden", {}, io.BytesIO(b"server body")
            )
            code, stdout, stderr, opener = self.run_cli(
                args, error=error, environ={"PARLAY_API_KEY": "offline-placeholder"}
            )
            self.assertEqual(code, 1)
            self.assertEqual(stdout, "")
            if args:
                self.assertIn("Check your key, allowance", stderr)
            else:
                self.assertIn("anonymous demo request was denied", stderr)
                self.assertIn("does not require an API key", stderr)
                self.assertNotIn("Check your key", stderr)
            self.assertNotIn("offline-placeholder", stderr)
            opener.open.assert_called_once()
            self.assertTrue(error.closed)

    def assert_contract_failure(self, payload, args=()):
        code, stdout, stderr, opener = self.run_cli(
            args,
            body=json.dumps(payload).encode(),
            environ={"PARLAY_API_KEY": "offline-placeholder"},
        )
        self.assertEqual(code, 1)
        self.assertEqual(stdout, "")
        self.assertIn("Response validation failed", stderr)
        self.assertIn("No CSV exported", stderr)
        self.assertNotIn("offline-placeholder", stderr)
        opener.open.assert_called_once()

    def test_demo_rejects_full_array_or_missing_demo_flag(self):
        for payload in (CAPTURE["events"], [], {"events": []}, {"demo": 1, "events": []}):
            self.assert_contract_failure(payload)

    def test_full_rejects_demo_wrapper(self):
        self.assert_contract_failure(CAPTURE, ["--full"])
        self.assert_contract_failure({"demo": True, "events": []}, ["--full"])

    def test_demo_rejects_more_than_five_events_before_deduplication(self):
        payload = copy.deepcopy(CAPTURE)
        payload["events"] *= 6
        self.assert_contract_failure(payload)

    def test_wrong_sport_rejects_whole_response_in_both_modes(self):
        payload = copy.deepcopy(CAPTURE)
        payload["events"][0]["sport_key"] = "soccer_epl"
        self.assert_contract_failure(payload)
        self.assert_contract_failure(payload["events"], ["--full"])

    def test_unrequested_market_rejects_whole_response(self):
        self.assert_contract_failure(CAPTURE["events"], ["--full", "--markets", "totals"])
        # Test-only structural mutation, not an observed spread or new market claim.
        payload = copy.deepcopy(CAPTURE)
        market = payload["events"][0]["bookmakers"][1]["markets"][0]
        market["key"] = "spreads"
        market["outcomes"][0]["point"] = 1.5
        market["outcomes"][1]["point"] = -1.5
        self.assert_contract_failure(payload)

    def test_full_matching_array_still_exports_source_rows(self):
        code, stdout, stderr, opener = self.run_cli(
            ["--full"],
            body=json.dumps(CAPTURE["events"]).encode(),
            environ={"PARLAY_API_KEY": "offline-placeholder"},
        )
        self.assertEqual(code, 0)
        self.assertEqual(len(list(csv.DictReader(io.StringIO(stdout)))), 2)
        self.assertIn("1 validation issues", stderr)
        opener.open.assert_called_once()

    def test_timeout_invalid_payload_or_oversize_response_fails_without_retry(self):
        for kwargs in (
            {"error": TimeoutError()},
            {"error": URLError("test offline")},
            {"body": b"not json"},
            {"body": b'{"error":"bad"}'},
            {"body": b"x" * 10_000_001},
        ):
            code, stdout, stderr, opener = self.run_cli(**kwargs)
            self.assertEqual(code, 1)
            self.assertEqual(stdout, "")
            self.assertIn("validation failed", stderr)
            opener.open.assert_called_once()

    def test_redirects_are_never_followed(self):
        handler = starter.NoRedirect()
        self.assertIsNone(
            handler.redirect_request(None, None, 302, None, None, "https://elsewhere.example")
        )

    def test_python_39_syntax_and_usage(self):
        ast.parse((HERE / "odds_workspace.py").read_text(), feature_version=(3, 9))
        with contextlib.redirect_stdout(io.StringIO()) as stdout:
            with self.assertRaises(SystemExit) as error:
                starter.main(["--help"])
        self.assertEqual(error.exception.code, 0)
        self.assertIn("--full", stdout.getvalue())
        self.assertIn("--no-include-live", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
