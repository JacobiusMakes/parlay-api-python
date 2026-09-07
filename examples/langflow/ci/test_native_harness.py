"""Lightweight false-positive and request-boundary checks; no browser required."""

import copy
import json
import os
import unittest
from pathlib import Path

from validate_native import EXPECTED, check_audit, final_audit, inspect_flow


class NativeHarnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        example = Path(os.environ.get("LANGFLOW_EXAMPLE_DIR", Path(__file__).resolve().parents[1]))
        cls.flow = json.loads((example / "Odds Sample Audit.json").read_text())
        cls.fixture = json.loads((example / "synthetic-odds.json").read_text())

    def request_template(self, flow):
        return next(n for n in flow["data"]["nodes"] if n["id"] == "APIRequest-fixture")["data"]["node"]["template"]

    def audit(self):
        return {
            **EXPECTED,
            "scope": "Synthetic fixture audit. No current odds or freshness claim.",
            "market_checks": [
                {
                    "bookmaker_key": book["key"],
                    "source_last_update": book.get("last_update"),
                    "timestamp_present": bool(book.get("last_update")),
                    "h2h_group_count": len(book["markets"]),
                    "outcomes": book["markets"][0]["outcomes"] if len(book["markets"]) == 1 else [],
                    "market_complete": index == 0,
                }
                for index, book in enumerate(self.fixture["events"][0]["bookmakers"])
            ],
        }

    def test_reviewed_flow_has_only_pinned_anonymous_fixture_request(self):
        self.assertIn("/synthetic-odds.json", inspect_flow(self.flow))

    def test_rejects_unpinned_foreign_authenticated_or_redirected_requests(self):
        mutations = [
            ("url_input", "https://parlay-api.com/v1/sports/baseball_mlb/odds"),
            ("url_input", "https://raw.githubusercontent.com/JacobiusMakes/parlay-api-python/main/examples/langflow/synthetic-odds.json"),
            ("url_input", inspect_flow(self.flow) + "?apiKey=UNIT_ONLY_CANARY"),
            ("headers", [{"key": "Authorization", "value": "UNIT_ONLY_CANARY"}]),
            ("method", "POST"),
            ("body", [{"key": "unexpected", "value": "unit-only"}]),
            ("follow_redirects", True),
            ("save_to_file", True),
        ]
        for field, value in mutations:
            with self.subTest(field=field, value=value):
                flow = copy.deepcopy(self.flow)
                self.request_template(flow)[field]["value"] = value
                with self.assertRaises(AssertionError):
                    inspect_flow(flow)

    def test_rejects_missing_node_even_if_other_settings_are_valid(self):
        flow = copy.deepcopy(self.flow)
        flow["data"]["nodes"] = [n for n in flow["data"]["nodes"] if n["id"] != "ParserComponent-report"]
        with self.assertRaises(AssertionError):
            inspect_flow(flow)

    def test_final_chat_output_is_required(self):
        entry = {"component_id": "ChatOutput-report", "results": {"message": {"text": json.dumps(self.audit())}}}
        self.assertEqual(final_audit({"outputs": [{"outputs": [entry]}]}), self.audit())
        entry["component_id"] = "DataOperations-audit"
        with self.assertRaises(AssertionError):
            final_audit({"outputs": [entry]})

    def test_counter_and_raw_source_fidelity_assertions(self):
        check_audit(self.audit(), self.fixture)
        mutations = [
            lambda a: a.update(complete_markets=3),
            lambda a: a["market_checks"][1].update(source_last_update="2030-01-01T12:00:00Z"),
            lambda a: a["market_checks"][0]["outcomes"][0].update(price=999),
            lambda a: a["market_checks"][2].update(market_complete=True),
        ]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                audit = copy.deepcopy(self.audit())
                mutate(audit)
                with self.assertRaises(AssertionError):
                    check_audit(audit, self.fixture)

    def test_accepts_native_parser_full_json_fence(self):
        text = "```json\n" + json.dumps(self.audit(), indent=2) + "\n```"
        entry = {"component_id": "ChatOutput-report", "results": {"message": {"text": text}}}
        self.assertEqual(final_audit({"outputs": [entry]}), self.audit())

    def test_rejects_fenced_json_with_surrounding_prose(self):
        text = "```json\n" + json.dumps(self.audit()) + "\n```"
        for decorated in ["Unverified summary\n" + text, text + "\nExtra output"]:
            with self.subTest(text=decorated):
                entry = {"component_id": "ChatOutput-report", "results": {"message": {"text": decorated}}}
                with self.assertRaises(AssertionError):
                    final_audit({"outputs": [entry]})


if __name__ == "__main__":
    unittest.main()
