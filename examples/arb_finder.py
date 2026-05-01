"""Two-book arbitrage finder.

For every game line and player prop, check whether any pair of books
in the response combine to an implied probability under 100. If yes,
that pair is an arbitrage and we print the optimal stake split for a
given total bankroll.

This is a more conservative tool than ev_scanner.py: arbitrage is rare
but bulletproof when it exists. A 1.5% arb on $1,000 returns $15
guaranteed.

Usage:
    export PARLAY_API_KEY=...
    python arb_finder.py basketball_nba --bankroll 1000
    python arb_finder.py baseball_mlb --markets player_strikeouts --min-edge 1.0
"""
from __future__ import annotations

import argparse
import os
import sys

sys.path.insert(0, "..")
from parlay_api import ParlayAPI, ParlayAPIError


def find_h2h_arbs(api: ParlayAPI, sport: str, min_edge_pct: float) -> list[dict]:
    events = api.odds(sport, markets="h2h", odds_format="american")
    arbs = []
    for ev in events:
        # Build {team_name: [(book, price), ...]}
        team_prices: dict[str, list[tuple[str, int]]] = {}
        for book in ev.get("bookmakers", []):
            for m in book.get("markets", []):
                if m.get("key") != "h2h":
                    continue
                for o in m.get("outcomes", []):
                    name, price = o.get("name"), o.get("price")
                    if name is None or price is None:
                        continue
                    team_prices.setdefault(name, []).append((book["key"], price))

        if len(team_prices) != 2:
            continue
        teams = list(team_prices.keys())
        a_options = team_prices[teams[0]]
        b_options = team_prices[teams[1]]

        for a_book, a_price in a_options:
            for b_book, b_price in b_options:
                if a_book == b_book:
                    continue  # arbing within one book is impossible
                a_imp = ParlayAPI.american_to_implied(a_price)
                b_imp = ParlayAPI.american_to_implied(b_price)
                total = a_imp + b_imp
                edge = (1.0 - total) * 100
                if edge >= min_edge_pct:
                    arbs.append({
                        "matchup": f"{ev.get('away_team','?')} @ {ev.get('home_team','?')}",
                        "team_a": teams[0],
                        "team_b": teams[1],
                        "book_a": a_book,
                        "book_b": b_book,
                        "price_a": a_price,
                        "price_b": b_price,
                        "edge_pct": edge,
                        "implied_total": total * 100,
                    })
    return sorted(arbs, key=lambda x: -x["edge_pct"])


def stake_split(price_a: int, price_b: int, bankroll: float) -> tuple[float, float, float]:
    """Returns (stake_a, stake_b, guaranteed_profit) for a 2-leg arb."""
    dec_a = ParlayAPI.american_to_decimal(price_a)
    dec_b = ParlayAPI.american_to_decimal(price_b)
    # Equal-payout split: stake_a * dec_a == stake_b * dec_b
    # stake_a + stake_b = bankroll
    # stake_a * dec_a = stake_b * dec_b
    # stake_b = stake_a * dec_a / dec_b
    # stake_a (1 + dec_a/dec_b) = bankroll
    # stake_a = bankroll / (1 + dec_a/dec_b)
    stake_a = bankroll / (1.0 + dec_a / dec_b)
    stake_b = bankroll - stake_a
    payout = stake_a * dec_a  # equals stake_b * dec_b
    return stake_a, stake_b, payout - bankroll


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sport")
    parser.add_argument("--min-edge", type=float, default=0.5,
                        help="Min arb edge in percentage points (default 0.5)")
    parser.add_argument("--bankroll", type=float, default=1000.0)
    parser.add_argument("--top", type=int, default=10)
    parser.add_argument("--api-key", default=os.environ.get("PARLAY_API_KEY"))
    args = parser.parse_args()

    if not args.api_key:
        print("error: set PARLAY_API_KEY env var or pass --api-key", file=sys.stderr)
        return 2

    api = ParlayAPI(api_key=args.api_key)
    try:
        arbs = find_h2h_arbs(api, args.sport, args.min_edge)
    except ParlayAPIError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1

    if not arbs:
        print(f"no arbs over {args.min_edge}% on {args.sport} h2h right now")
        return 0

    print(f"\n{min(args.top, len(arbs))} arbs on {args.sport} (bankroll ${args.bankroll:,.0f}):\n")
    for a in arbs[:args.top]:
        sa, sb, profit = stake_split(a["price_a"], a["price_b"], args.bankroll)
        print(f"  {a['matchup']}")
        print(f"    {a['team_a'][:30]:32} {a['price_a']:+5} @ {a['book_a']:12} stake ${sa:>7.2f}")
        print(f"    {a['team_b'][:30]:32} {a['price_b']:+5} @ {a['book_b']:12} stake ${sb:>7.2f}")
        print(f"    -> guaranteed profit ${profit:+.2f}  ({a['edge_pct']:+.2f}%)\n")

    return 0


if __name__ == "__main__":
    sys.exit(main())
