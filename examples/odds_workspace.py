#!/usr/bin/env python3
"""Export one ParlayAPI odds response to CSV. Python 3.9+, standard library only.

No key or package installation is needed for the default demo request:
    python3 odds_workspace.py > odds.csv
    python3 odds_workspace.py --sport americanfootball_nfl > odds.csv

For an explicit full request, set PARLAY_API_KEY in your terminal first:
    python3 odds_workspace.py --full --markets h2h,spreads,totals > odds.csv
    python3 odds_workspace.py --full --no-include-live > pregame.csv

Demo mode ignores PARLAY_API_KEY and is always first-five US moneyline events.
Full mode includes commenced games by default, with include_live explicit in the
request. There are no automatic retries, polling, redirects or key persistence.
CSV contains source prices and timestamps, with ambiguous groups excluded.
Configure a matching request visually: https://parlay-api.com/playground#project

MIT License. Copyright (c) 2026 Jacob. See the repository LICENSE.
"""

import argparse
import csv
import io
import json
import math
import os
import re
import sys
from collections import Counter
from datetime import datetime
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, build_opener, HTTPRedirectHandler

SPORTS = {
    "baseball_mlb",
    "basketball_nba",
    "americanfootball_nfl",
    "icehockey_nhl",
    "soccer_epl",
    "mma_mixed_martial_arts",
}
MARKETS = {"h2h", "spreads", "totals"}
CSV_FIELDS = [
    "event_id",
    "sport_key",
    "home_team",
    "away_team",
    "commence_time",
    "bookmaker_key",
    "bookmaker_title",
    "bookmaker_last_update",
    "market_key",
    "market_last_update",
    "outcome_name",
    "point",
    "price",
]


def is_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def is_text(value):
    return (
        isinstance(value, str)
        and 0 < len(value) <= 200
        and value.strip() == value
        and not re.search(r"[\x00-\x1f\x7f]", value)
    )


def is_key(value):
    return (
        isinstance(value, str)
        and re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}", value) is not None
    )


def inspect_sample(payload):
    rows, issues = [], []
    source = (
        payload
        if isinstance(payload, list)
        else payload.get("events")
        if isinstance(payload, dict) and payload.get("demo") is True
        else None
    )
    if not isinstance(source, list) or len(source) > 5000:
        raise ValueError("Expected an event array or demo events array, maximum 5,000 events")

    def issue(code, event_id=None, book_key=None, market_key=None):
        issues.append(
            {"code": code, "eventId": event_id, "bookmakerKey": book_key, "marketKey": market_key}
        )

    def counts(items, field):
        return Counter(
            item[field] for item in items if isinstance(item, dict) and is_key(item.get(field))
        )

    def stamp(value, event_id, book_key=None, market_key=None):
        if value is None:
            return None
        try:
            if not is_text(value) or not re.fullmatch(
                r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:\d{2})", value
            ):
                raise ValueError()
            datetime.fromisoformat(value.replace("Z", "+00:00"))
            return value
        except ValueError:
            issue("invalid_timestamp", event_id, book_key, market_key)
            return None

    ids, canonical_ids = counts(source, "id"), counts(source, "canonical_event_id")
    seen = set()
    for event in source:
        if (
            not isinstance(event, dict)
            or not is_key(event.get("id"))
            or not isinstance(event.get("sport_key"), str)
            or event["sport_key"] not in SPORTS
            or not is_text(event.get("home_team"))
            or not is_text(event.get("away_team"))
            or event["home_team"] == event["away_team"]
            or not isinstance(event.get("bookmakers"), list)
            or len(event["bookmakers"]) > 1000
        ):
            issue(
                "invalid_event",
                event.get("id") if isinstance(event, dict) and is_key(event.get("id")) else None,
            )
            continue
        event_id = event["id"]
        if ids[event_id] > 1 or (
            is_key(event.get("canonical_event_id"))
            and canonical_ids[event["canonical_event_id"]] > 1
        ):
            if event_id not in seen:
                issue("duplicate_event", event_id)
            seen.add(event_id)
            continue
        commence = stamp(event.get("commence_time"), event_id)
        book_counts, visited_books = counts(event["bookmakers"], "key"), set()
        for book in event["bookmakers"]:
            if (
                not isinstance(book, dict)
                or not is_key(book.get("key"))
                or not isinstance(book.get("markets"), list)
                or len(book["markets"]) > 100
            ):
                issue("invalid_bookmaker", event_id)
                continue
            book_key = book["key"]
            if book_counts[book_key] > 1:
                if book_key not in visited_books:
                    issue("duplicate_bookmaker", event_id, book_key)
                visited_books.add(book_key)
                continue
            book_stamp = stamp(book.get("last_update"), event_id, book_key)
            market_counts, visited_markets = counts(book["markets"], "key"), set()
            for market in book["markets"]:
                if (
                    not isinstance(market, dict)
                    or not isinstance(market.get("key"), str)
                    or market["key"] not in MARKETS
                ):
                    issue("unsupported_market", event_id, book_key)
                    continue
                market_key = market["key"]
                if market_counts[market_key] > 1:
                    if market_key not in visited_markets:
                        issue("duplicate_market", event_id, book_key, market_key)
                    visited_markets.add(market_key)
                    continue
                outcomes = market.get("outcomes")
                valid = isinstance(outcomes, list) and 2 <= len(outcomes) <= (
                    3 if market_key == "h2h" else 2
                )
                names = set()
                if valid:
                    for outcome in outcomes:
                        if (
                            not isinstance(outcome, dict)
                            or not is_text(outcome.get("name"))
                            or outcome["name"] in names
                            or not is_number(outcome.get("price"))
                            or abs(outcome["price"]) < 100
                        ):
                            valid = False
                            break
                        names.add(outcome["name"])
                        if market_key == "h2h":
                            valid = (
                                valid
                                and outcome.get("point") is None
                                and outcome["name"]
                                in (event["home_team"], event["away_team"], "Draw")
                            )
                        elif market_key == "spreads":
                            valid = (
                                valid
                                and is_number(outcome.get("point"))
                                and outcome["name"] in (event["home_team"], event["away_team"])
                            )
                        else:
                            valid = (
                                valid
                                and is_number(outcome.get("point"))
                                and outcome["name"] in ("Over", "Under")
                            )
                    if market_key in ("h2h", "spreads"):
                        valid = (
                            valid and event["home_team"] in names and event["away_team"] in names
                        )
                    if valid and market_key == "spreads":
                        valid = outcomes[0]["point"] == -outcomes[1]["point"]
                    if valid and market_key == "totals":
                        valid = (
                            "Over" in names
                            and "Under" in names
                            and outcomes[0]["point"] == outcomes[1]["point"]
                        )
                if not valid:
                    issue("invalid_outcomes", event_id, book_key, market_key)
                    continue
                market_stamp = stamp(market.get("last_update"), event_id, book_key, market_key)
                for outcome in outcomes:
                    rows.append(
                        {
                            "event_id": event_id,
                            "sport_key": event["sport_key"],
                            "home_team": event["home_team"],
                            "away_team": event["away_team"],
                            "commence_time": commence,
                            "bookmaker_key": book_key,
                            "bookmaker_title": book.get("title")
                            if is_text(book.get("title"))
                            else None,
                            "bookmaker_last_update": book_stamp,
                            "market_key": market_key,
                            "market_last_update": market_stamp,
                            "outcome_name": outcome["name"],
                            "point": outcome.get("point"),
                            "price": outcome["price"],
                        }
                    )
    return rows, issues


def to_csv(rows):
    def cell(value):
        if value is None:
            return ""
        if is_number(value):
            return value
        value = str(value)
        if re.match(r"^[\s\ufeff]*[=+\-@]", value) or re.match(r"^[\t\r\n]", value):
            value = "'" + value
        return value

    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    writer.writerow(CSV_FIELDS)
    for row in rows:
        writer.writerow([cell(row.get(field)) for field in CSV_FIELDS])
    return output.getvalue()


class NoRedirect(HTTPRedirectHandler):
    # Never forward the API key to a redirect destination.
    def redirect_request(self, request, fp, code, msg, headers, newurl):
        return None


def parse_markets(value):
    requested = value.split(",")
    if not requested or any(market not in MARKETS for market in requested):
        raise argparse.ArgumentTypeError("use h2h, spreads or totals, separated by commas")
    return [market for market in ("h2h", "spreads", "totals") if market in requested]


def parse_args(argv=None):
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--sport",
        choices=sorted(SPORTS),
        default="baseball_mlb",
        help="one sport; default: baseball_mlb",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="make a full API request using PARLAY_API_KEY; consumes account credits",
    )
    parser.add_argument(
        "--markets",
        type=parse_markets,
        default=["h2h"],
        help="full mode: h2h,spreads,totals; default: h2h",
    )
    parser.add_argument(
        "--include-live",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="full mode: include commenced games; enabled by default; --no-include-live requests pregame",
    )
    args = parser.parse_args(argv)
    if not args.full and (args.markets != ["h2h"] or args.include_live is not None):
        parser.error(
            "market and live filters require --full. The demo always returns US moneyline; it accepts no live filter."
        )
    return args


def request_url(args):
    if not args.full:
        return "https://parlay-api.com/v1/try/" + args.sport + "/odds"
    params = {
        "regions": "us",
        "markets": ",".join(args.markets),
        "oddsFormat": "american",
        "dateFormat": "iso",
        "include_live": "false" if args.include_live is False else "true",
    }
    return "https://parlay-api.com/v1/sports/" + args.sport + "/odds?" + urlencode(params)


class ResponseContractError(ValueError):
    """A response does not match the explicit request mode or filters."""


def validate_response(payload, args):
    if args.full:
        if not isinstance(payload, list):
            raise ResponseContractError("full mode requires an event array")
        events = payload
    else:
        if (
            not isinstance(payload, dict)
            or payload.get("demo") is not True
            or not isinstance(payload.get("events"), list)
            or len(payload["events"]) > 5
        ):
            raise ResponseContractError(
                "demo mode requires a demo wrapper with at most five events"
            )
        events = payload["events"]
    if any(not isinstance(event, dict) or event.get("sport_key") != args.sport for event in events):
        raise ResponseContractError("returned events do not match the requested sport")
    rows, issues = inspect_sample(payload)
    if any(row["market_key"] not in args.markets for row in rows):
        raise ResponseContractError("returned markets do not match the requested markets")
    return rows, issues


def main(argv=None):
    args = parse_args(argv)
    headers = {"Accept": "application/json"}
    if args.full:
        api_key = os.environ.get("PARLAY_API_KEY", "").strip()
        if not api_key or "\n" in api_key or "\r" in api_key:
            print(
                "Set PARLAY_API_KEY in your terminal for --full. Or omit --full to try the no-key demo.",
                file=sys.stderr,
            )
            return 2
        headers["X-API-Key"] = api_key
        print(
            "Full API: one US-region request with explicit markets and include_live. Account credits apply.",
            file=sys.stderr,
        )
    else:
        print(
            "Demo: first five US moneyline events; shared limit 60 requests/hour per IP. PARLAY_API_KEY is ignored.",
            file=sys.stderr,
        )
    request = Request(request_url(args), headers=headers)
    try:
        with build_opener(NoRedirect()).open(request, timeout=30) as response:
            if response.status != 200:
                raise ValueError("Expected HTTP 200")
            body = response.read(10_000_001)
            if len(body) > 10_000_000:
                raise ValueError("Response exceeds the 10 MB safety limit")
            payload = json.loads(body)
        rows, issues = validate_response(payload, args)
    except HTTPError as error:
        retry = error.headers.get("Retry-After") if error.headers else None
        suffix = " Retry-After: " + str(retry)[:80] if error.code == 429 and retry else ""
        print(
            "Request failed: HTTP "
            + str(error.code)
            + ". Check your key, allowance and request settings."
            + suffix,
            file=sys.stderr,
        )
        error.close()
        return 1
    except ResponseContractError as error:
        print("Response validation failed: " + str(error) + ". No CSV exported.", file=sys.stderr)
        return 1
    except (URLError, TimeoutError, OSError, ValueError, TypeError) as error:
        print(
            "Request or response validation failed ("
            + type(error).__name__
            + "). Check connectivity and the API response. No automatic retry.",
            file=sys.stderr,
        )
        return 1
    sys.stdout.write(to_csv(rows))
    print(
        str(len(rows))
        + " source rows exported; "
        + str(len(issues))
        + " validation issues. Timestamps are source fields, not freshness guarantees.",
        file=sys.stderr,
    )
    for issue in issues[:25]:
        print(json.dumps(issue, ensure_ascii=True), file=sys.stderr)
    if not rows:
        print(
            "No usable rows returned. This response does not establish coverage or explain why data is absent.",
            file=sys.stderr,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
