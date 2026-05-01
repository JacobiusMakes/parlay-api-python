"""Subscribe to live odds updates over WebSocket.

Streams every odds change for a given sport in real time. Useful for
+EV scanners that need to react faster than 60-second REST polling.

Requires Business tier or above.

Usage:
    pip install websockets
    export PARLAY_API_KEY=...
    python websocket_stream.py basketball_nba
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime

try:
    import websockets
except ImportError:
    print("install websockets: pip install websockets", file=sys.stderr)
    raise

sys.path.insert(0, "..")
from parlay_api import ParlayAPI


async def stream(api: ParlayAPI, sport: str, event_filter: str | None = None) -> None:
    url = api.websocket_url(sport)
    print(f"connecting to {url}")
    async with websockets.connect(url, ping_interval=20) as ws:
        if event_filter:
            await ws.send(json.dumps({
                "type": "subscribe",
                "event_id": event_filter,
            }))
            print(f"subscribed to event_id={event_filter}")

        seen_initial = False
        while True:
            raw = await ws.recv()
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                print(f"non-json frame: {raw[:80]}")
                continue

            now = datetime.utcnow().strftime("%H:%M:%S")
            mtype = msg.get("type", "?")
            if mtype == "odds_update" and not seen_initial:
                seen_initial = True
                count = msg.get("count") or len(msg.get("data") or [])
                print(f"[{now}] initial snapshot: {count} props")
                continue
            if mtype == "odds_update":
                data = msg.get("data") or []
                # Show a couple of representative changes
                for r in data[:3]:
                    print(f"[{now}] {r.get('bookmaker','?'):12} "
                          f"{r.get('player_name','?')[:24]:24} "
                          f"{r.get('market_key','?'):20} "
                          f"line={r.get('line','?')} "
                          f"O{r.get('over_price','?')} U{r.get('under_price','?')}")
            else:
                print(f"[{now}] {mtype}: {str(msg)[:140]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("sport")
    parser.add_argument("--event", help="filter to one event_id")
    parser.add_argument("--api-key", default=os.environ.get("PARLAY_API_KEY"))
    args = parser.parse_args()

    if not args.api_key:
        print("error: set PARLAY_API_KEY env var or pass --api-key", file=sys.stderr)
        return 2

    api = ParlayAPI(api_key=args.api_key)
    try:
        asyncio.run(stream(api, args.sport, args.event))
    except KeyboardInterrupt:
        print("\nstopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
