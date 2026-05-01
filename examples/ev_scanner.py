"""Cross-book +EV scanner using ParlayAPI.

Pulls a sport's player props from every book ParlayAPI tracks, picks
the sharpest book in the lineup as the "true probability" baseline,
devigs that book's prices, and then surfaces every other book where a
posted price implies a probability lower than the fair probability by
more than the threshold (default 3 percentage points).

This is the kind of tool davpwave was building. Run it as-is, or read
it as a template for your own model.

Usage:
    export PARLAY_API_KEY=...
    python ev_scanner.py baseball_mlb player_strikeouts --edge 3.0
    python ev_scanner.py basketball_nba player_points --edge 5.0 --top 30
    python ev_scanner.py icehockey_nhl player_shots_on_goal --baseline pinnacle
"""
from __future__ import annotations

import argparse
import os
import sys
from collections import defaultdict
from dataclasses import dataclass

# Adjust if you've installed the SDK with pip
sys.path.insert(0, "..")
from parlay_api import ParlayAPI, ParlayAPIError

# Books we treat as "sharp enough" to use as a fair-price baseline. The
# order matters: we use the first one in this list that has a price for
# a given (player, market, line). Pinnacle is the canonical reference,
# Novig and ProphetX are exchanges (peer-to-peer, no vig in the
# theoretical limit), bet365 has the tightest market on US books.
DEFAULT_BASELINES = ["pinnacle", "novig", "prophetx", "bet365"]


@dataclass
class Edge:
    player: str
    market: str
    line: float
    book: str
    side: str            # "Over" or "Under"
    book_price: int
    book_implied: float  # what the book's price implies
    fair_prob: float     # baseline-devigged probability
    edge_pct: float      # fair - book_implied, in percentage points
    baseline_book: str
    baseline_price: int


def find_edges(
    api: ParlayAPI,
    sport: str,
    market: str,
    baselines: list[str],
    edge_threshold_pct: float,
) -> list[Edge]:
    rows = api.props(sport, markets=[market])
    if not rows:
        return []

    # Group rows by (player, market_key, line) so we can find both sides
    grouped: dict[tuple[str, str, float], dict[str, dict]] = defaultdict(dict)
    for r in rows:
        key = (
            r.get("player_name") or r.get("player") or "",
            r.get("market_key") or "",
            float(r.get("line") or 0.0),
        )
        if not key[0]:
            continue
        book = r.get("bookmaker") or r.get("source")
        if not book:
            continue
        grouped[key][book] = r

    edges: list[Edge] = []

    for (player, mkt, line), books in grouped.items():
        baseline = _pick_baseline(books, baselines)
        if baseline is None:
            continue
        bbook, brow = baseline
        b_over = brow.get("over_price")
        b_under = brow.get("under_price")
        if b_over is None or b_under is None:
            continue

        try:
            fair_over, fair_under = ParlayAPI.devig(b_over, b_under)
        except ValueError:
            continue

        # Compare every book's posted price (Over and Under separately)
        # against the baseline-devigged fair probability.
        for book, row in books.items():
            if book == bbook:
                continue
            for side, fair_p, book_price in (
                ("Over", fair_over, row.get("over_price")),
                ("Under", fair_under, row.get("under_price")),
            ):
                if book_price is None:
                    continue
                book_implied = ParlayAPI.american_to_implied(book_price)
                edge_pp = (fair_p - book_implied) * 100
                if edge_pp >= edge_threshold_pct:
                    edges.append(Edge(
                        player=player,
                        market=mkt,
                        line=line,
                        book=book,
                        side=side,
                        book_price=int(book_price),
                        book_implied=book_implied,
                        fair_prob=fair_p,
                        edge_pct=edge_pp,
                        baseline_book=bbook,
                        baseline_price=int(b_over if side == "Over" else b_under),
                    ))

    edges.sort(key=lambda e: -e.edge_pct)
    return edges


def _pick_baseline(books: dict[str, dict], preference: list[str]) -> tuple[str, dict] | None:
    """Pick the sharpest available book that has both Over and Under priced."""
    for pref in preference:
        if pref in books:
            row = books[pref]
            if row.get("over_price") is not None and row.get("under_price") is not None:
                return (pref, row)
    return None


def fmt_price(price: int) -> str:
    return f"+{price}" if price > 0 else str(price)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sport", help="e.g. baseball_mlb, basketball_nba, icehockey_nhl")
    parser.add_argument("market", help="e.g. player_points, player_strikeouts")
    parser.add_argument("--edge", type=float, default=3.0,
                        help="Edge threshold in percentage points (default 3.0)")
    parser.add_argument("--top", type=int, default=20,
                        help="Show top N edges (default 20)")
    parser.add_argument("--baseline", nargs="+", default=DEFAULT_BASELINES,
                        help=f"Baseline books, in order (default {DEFAULT_BASELINES})")
    parser.add_argument("--api-key", default=os.environ.get("PARLAY_API_KEY"),
                        help="ParlayAPI key (env: PARLAY_API_KEY)")
    args = parser.parse_args()

    if not args.api_key:
        print("error: set PARLAY_API_KEY env var or pass --api-key", file=sys.stderr)
        return 2

    api = ParlayAPI(api_key=args.api_key)
    try:
        edges = find_edges(api, args.sport, args.market,
                           baselines=args.baseline,
                           edge_threshold_pct=args.edge)
    except ParlayAPIError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if not edges:
        print(f"no +{args.edge:.1f}% edges found on {args.sport} / {args.market}")
        return 0

    print(f"\nTop {min(args.top, len(edges))} +EV bets on "
          f"{args.sport} / {args.market} (baseline: {args.baseline}):\n")
    print(f"{'Player':22} {'Line':>5} {'Side':5} {'Book':12} {'Price':6} "
          f"{'Implied':>8} {'Fair':>8} {'Edge':>7}")
    print("-" * 86)
    for e in edges[:args.top]:
        print(f"{e.player[:22]:22} {e.line:5.1f} {e.side:5} {e.book:12} "
              f"{fmt_price(e.book_price):>6} {e.book_implied*100:>6.1f}%  "
              f"{e.fair_prob*100:>6.1f}%  {e.edge_pct:>+5.1f}pp")

    print(f"\nQuota: {api.last_quota}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
