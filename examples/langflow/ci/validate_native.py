"""Hosted native Langflow check. No provider key or live odds request is used."""

import argparse
import hashlib
import importlib.metadata
import json
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import urlsplit


BASE = "http://127.0.0.1:7860"
NODE_IDS = {
    "APIRequest-fixture",
    "DataOperations-audit",
    "ParserComponent-report",
    "ChatOutput-report",
}
EXPECTED = {
    "event_count": 1,
    "complete_markets": 1,
    "incomplete_or_ambiguous_markets": 2,
    "missing_source_timestamps": 1,
}


def inspect_flow(flow):
    """Fail before starting the flow if the example could request account data."""
    nodes = flow["data"]["nodes"]
    executable = [n for n in nodes if n["type"] != "noteNode"]
    assert {n["id"] for n in executable} == NODE_IDS
    assert len(executable) == 4
    assert len(flow["data"]["edges"]) == 3
    api = next(n for n in executable if n["id"] == "APIRequest-fixture")
    template = api["data"]["node"]["template"]
    values = {k: v.get("value") for k, v in template.items() if isinstance(v, dict)}
    url = values["url_input"]
    assert re.fullmatch(
        r"https://raw\.githubusercontent\.com/JacobiusMakes/parlay-api-python/"
        r"[0-9a-f]{40}/examples/langflow/synthetic-odds\.json", url
    ), "Fixture must use the exact owned repository, full commit, and JSON path"
    assert values["method"] == "GET" and values["mode"] == "URL"
    assert values["headers"] == [{"key": "Accept", "value": "application/json"}]
    assert values["body"] == [] and not values["query_params"] and not values["curl_input"]
    assert values["follow_redirects"] is False and values["save_to_file"] is False
    assert values["timeout"] == 30
    output = next(n for n in executable if n["id"] == "ChatOutput-report")
    assert output["data"]["node"]["template"]["should_store_message"]["value"] is False
    return url


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def verify_published_fixture(url, local_bytes):
    """Use real immutable public bytes; never substitute a successful response."""
    opener = urllib.request.build_opener(NoRedirect, urllib.request.ProxyHandler({}))
    request = urllib.request.Request(url, headers={"Accept": "application/json"})
    with opener.open(request, timeout=30) as response:
        assert response.status == 200
        remote = response.read(200_001)
    assert len(remote) <= 200_000
    assert remote == local_bytes, "Published fixture must match reviewed checkout bytes"
    assert json.loads(remote)["synthetic"] is True
    return hashlib.sha256(remote).hexdigest()


def walk(value):
    yield value
    if isinstance(value, dict):
        for item in value.values():
            yield from walk(item)
    elif isinstance(value, list):
        for item in value:
            yield from walk(item)


def final_message_texts(response):
    """Select text from the final Chat Output component only."""
    texts = []
    for item in walk(response):
        if not isinstance(item, dict) or item.get("component_id") != "ChatOutput-report":
            continue
        message = item.get("results", {}).get("message")
        for field in walk(message):
            if not isinstance(field, dict) or not isinstance(field.get("text"), str):
                continue
            texts.append(field["text"])
    return texts


def final_audit(response):
    """Require final Chat Output JSON, optionally in Langflow's full JSON fence."""
    found = []
    for text in final_message_texts(response):
        text = text.strip()
        # Langflow 1.12 Parser Stringify uses safe_convert(Data), which emits
        # exactly a JSON Markdown fence. Do not search arbitrary surrounding prose.
        fenced = re.fullmatch(r"```json[ \t]*\r?\n(.*?)\r?\n```", text, flags=re.DOTALL)
        if fenced:
            text = fenced.group(1)
        try:
            parsed = json.loads(text)
        except ValueError:
            continue
        if isinstance(parsed, dict) and set(EXPECTED).issubset(parsed):
            found.append(parsed)
    assert found, "Native final Chat Output did not contain the audit JSON"
    assert all(item == found[0] for item in found), "Conflicting final outputs"
    return found[0]


def check_audit(audit, fixture):
    assert {k: audit.get(k) for k in EXPECTED} == EXPECTED
    assert audit["scope"] == "Synthetic fixture audit. No current odds or freshness claim."
    checks = audit["market_checks"]
    books = fixture["events"][0]["bookmakers"]
    assert len(checks) == len(books) == 3
    for check, book in zip(checks, books):
        assert check["bookmaker_key"] == book["key"]
        assert check["source_last_update"] == book.get("last_update")
        assert check["timestamp_present"] == bool(book.get("last_update"))
        markets = [m for m in book["markets"] if m["key"] == "h2h"]
        assert check["h2h_group_count"] == len(markets)
        assert check["outcomes"] == (markets[0]["outcomes"] if len(markets) == 1 else [])
    assert [item["market_complete"] for item in checks] == [True, False, False]


def validate(example_dir, artifacts):
    from playwright.sync_api import expect, sync_playwright

    report = {"status": "failed", "stage": "preflight", "checks": [],
              "configured_live_odds_requests": 0, "response_mocking": False,
              "page_errors": [], "blocked_browser_origins": []}
    browser = None
    page = None
    try:
        flow_bytes = (example_dir / "Odds Sample Audit.json").read_bytes()
        fixture_bytes = (example_dir / "synthetic-odds.json").read_bytes()
        flow = json.loads(flow_bytes)
        fixture = json.loads(fixture_bytes)
        report["fixture_url"] = inspect_flow(flow)
        report["fixture_sha256"] = verify_published_fixture(report["fixture_url"], fixture_bytes)
        report["flow_sha256"] = hashlib.sha256(flow_bytes).hexdigest()
        report["versions"] = {name: importlib.metadata.version(name)
                              for name in ["langflow", "langflow-base", "lfx", "playwright", "jq"]}
        assert all(report["versions"][name] == "1.12.0"
                   for name in ["langflow", "langflow-base", "lfx"])
        report["checks"].append("Published immutable fixture matches reviewed synthetic bytes")
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            context = browser.new_context(viewport={"width": 1600, "height": 1200})

            def browser_route(route):
                url = urlsplit(route.request.url)
                if f"{url.scheme}://{url.netloc}" == BASE:
                    route.continue_()
                else:
                    origin = f"{url.scheme}://{url.netloc}"
                    if origin not in report["blocked_browser_origins"]:
                        report["blocked_browser_origins"].append(origin)
                    route.abort()

            context.route("**/*", browser_route)
            report["stage"] = "server readiness"
            deadline = time.monotonic() + 210
            while True:
                try:
                    ready = context.request.get(BASE + "/health", timeout=3000)
                    if ready.ok:
                        break
                except Exception:
                    pass
                assert time.monotonic() < deadline, "Local Langflow health check timed out"
                time.sleep(2)

            report["stage"] = "local session and native import"
            session = context.request.get(BASE + "/api/v1/auto_login")
            assert session.ok, f"Local auto-login returned HTTP {session.status}"
            # Cookies remain only in this disposable browser context, never artifacts.
            imported = context.request.post(BASE + "/api/v1/flows/upload/", multipart={
                "file": {"name": "Odds Sample Audit.json", "mimeType": "application/json", "buffer": flow_bytes}
            }, timeout=60_000)
            assert imported.status == 201, f"Native flow upload returned HTTP {imported.status}"
            imported_flows = imported.json()
            assert isinstance(imported_flows, list) and len(imported_flows) == 1
            saved = imported_flows[0]
            assert saved["name"] == flow["name"]
            assert inspect_flow(saved) == report["fixture_url"]
            flow_id = saved["id"]
            report["flow_id"] = flow_id
            report["checks"].append("Native upload imported all four nodes, three edges, and safe request settings")

            report["stage"] = "native editor screenshot"
            page = context.new_page()
            page.on("pageerror", lambda error: report["page_errors"].append(str(error)[:500]))
            page.goto(BASE + "/flow/" + flow_id, wait_until="domcontentloaded", timeout=90_000)
            for node_id in sorted(NODE_IDS):
                expect(page.locator(f'.react-flow__node[data-id="{node_id}"]')).to_be_visible(timeout=90_000)
            expect(page.locator(".react-flow__edge")).to_have_count(3)
            instruction = page.locator('.react-flow__node[data-id="note-setup"]').get_by_text(
                "Run the final Chat Output component", exact=False
            )
            expect(instruction).to_be_visible()
            expect(instruction).to_be_in_viewport()
            page.screenshot(path=str(artifacts / "native-editor.png"), full_page=True)
            report["checks"].append("Actual Langflow editor displays four component nodes, three edges, and the Run instruction")

            report["stage"] = "native execution"
            result = context.request.post(BASE + f"/api/v1/run/session/{flow_id}?stream=false", data={
                "input_value": "", "input_type": "chat", "output_type": "chat", "tweaks": {}
            }, timeout=90_000)
            assert result.ok, f"Native execution returned HTTP {result.status}"
            response_data = result.json()
            # The validated flow has only a public synthetic fixture and no keys.
            # Retain only final message text, never session/cookie/response metadata.
            diagnostics = [re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]", "", text)[:50_000]
                           for text in final_message_texts(response_data)]
            (artifacts / "native-final-messages.json").write_text(json.dumps(diagnostics, indent=2) + "\n")
            audit = final_audit(response_data)
            check_audit(audit, fixture)
            (artifacts / "native-output.json").write_text(json.dumps(audit, indent=2) + "\n")
            report["checks"].append("Final native Chat Output has expected 1/1/2/1 counters and exact synthetic source values")
            assert not report["page_errors"], "Unexpected native editor JavaScript errors"
            report["status"] = "passed"
            report["stage"] = "complete"
            context.close()
            browser.close()
            browser = None
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        if page:
            try:
                page.screenshot(path=str(artifacts / "failure.png"), full_page=True)
            except Exception:
                pass
        raise
    finally:
        if browser:
            try:
                browser.close()
            except Exception:
                pass
        (artifacts / "report.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps({"status": report["status"], "stage": report["stage"], "checks": len(report["checks"])}))


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--example-dir", type=Path, required=True)
    parser.add_argument("--artifacts", type=Path, required=True)
    args = parser.parse_args()
    args.artifacts.mkdir(parents=True, exist_ok=True)
    validate(args.example_dir, args.artifacts)
