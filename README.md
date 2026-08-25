# parlay-api

Python SDK for [parlay-api.com](https://parlay-api.com), a drop-in
replacement for [the-odds-api.com](https://the-odds-api.com) with 45+
sportsbooks & sources, player props, prediction markets, and WebSocket
streaming.

```bash
pip install parlay-api
```

```python
from parlay_api import ParlayAPI

client = ParlayAPI(api_key="YOUR_KEY")
events = client.odds("baseball_mlb", regions="us", markets="h2h,spreads,totals")
```

## Why

The-odds-api is fine but ships flat -115/-115 placeholders for half
the props you actually want, costs 5 to 6 times more at the Enterprise
tier, and has no streaming. ParlayAPI ships real American odds across
45+ sportsbooks & sources, integrates Polymarket as a sharp
prediction-market baseline, and runs WebSockets on Business+ tiers.

The SDK preserves TOA's endpoint shape, so migration is one config
change.

## Migration from the-odds-api

If you're currently using the unofficial Python client:

```python
# before
from the_odds_api import OddsAPI
client = OddsAPI(api_key=KEY)
events = client.get_odds(sport_key="basketball_nba", ...)

# after, three-line diff
from parlay_api import ParlayAPI
client = ParlayAPI(api_key=KEY)
events = client.odds("basketball_nba", ...)
```

If you're calling TOA via raw HTTP, just swap the base URL:

```python
# before
url = "https://api.the-odds-api.com/v4/sports/basketball_nba/odds"

# after
url = "https://parlay-api.com/v4/sports/basketball_nba/odds"
```

Same paths (`/v4/sports`, `/v4/sports/{sport}/odds`,
`/v4/sports/{sport}/events`, `/v4/sports/{sport}/scores`,
`/v4/historical/sports/{sport}/odds`), same response shapes, same
query parameters (`regions`, `markets`, `bookmakers`, `oddsFormat`,
`dateFormat`, `eventIds`, `commenceTimeFrom`, `commenceTimeTo`).

## What's different from TOA

Beyond TOA's endpoints, ParlayAPI exposes:

| Endpoint | What |
|---|---|
| `GET /v1/sports/{sport}/props` | Flat list of paired O/U player props across every source |
| `GET /v1/sports/{sport}/props/markets` | Available prop market keys + which books offer each |
| `GET /v1/sports/{sport}/futures` | Outrights and championship futures grouped by competition |
| `GET /v1/usage` | Current API key usage state (tier, credits used, credits remaining) |
| `WSS /ws/odds/{sport}?apiKey=` | Live odds stream, Business+ tier |

Plus `markets=player_*` works on the standard `/v4/sports/{sport}/odds`
endpoint, returning paired Over/Under in TOA's exact event shape.

## Quickstart

```python
from parlay_api import ParlayAPI

client = ParlayAPI(api_key="YOUR_KEY")

# List sports
print([s["key"] for s in client.sports()])

# h2h + spreads + totals across every book
events = client.odds(
    "basketball_nba",
    regions="us",
    markets="h2h,spreads,totals",
    odds_format="american",
)

# Player props (TOA-shaped)
prop_events = client.odds(
    "baseball_mlb",
    markets="player_strikeouts,player_total_bases,player_hits",
)

# Player props (flat list, ParlayAPI-extension)
rows = client.props(
    "baseball_mlb",
    markets=["player_strikeouts"],
    bookmakers=["draftkings", "pinnacle", "fanduel", "bet365"],
)
for r in rows[:10]:
    print(r["bookmaker"], r["player_name"], r["line"], r["over_price"], "/", r["under_price"])

# Devig a paired market on the client side, no network
fair_over, fair_under = ParlayAPI.devig(over_price=-110, under_price=-110)
# fair_over == 0.5, fair_under == 0.5

# Compute a +EV edge in percentage points
edge = ParlayAPI.edge(book_price=+120, fair_prob=0.55)
# +9.5pp positive expected value
```

## WebSocket streaming (Business+)

```bash
pip install parlay-api[ws]
```

```python
import asyncio, json, websockets
from parlay_api import ParlayAPI

client = ParlayAPI(api_key="YOUR_KEY")

async def run():
    async with websockets.connect(client.websocket_url("baseball_mlb")) as ws:
        while True:
            msg = json.loads(await ws.recv())
            print(msg.get("type"), len(msg.get("data") or []))

asyncio.run(run())
```

You'll receive an initial snapshot frame (`type=odds_update` with the
full current state) followed by push frames whenever any book
updates a price. Optional event-level filter:

```python
await ws.send(json.dumps({
    "type": "subscribe",
    "event_id": "2026-04-29_New_York_Yankees_Boston_Red_Sox",
}))
```

## Examples

The [`examples/`](./examples/) folder ships three runnable scripts:

- **`ev_scanner.py`** — pulls a sport's player props, devigs the
  sharpest book in each market as the fair-price baseline, and prints
  every other book's posted line that exceeds a +3pp edge threshold.
  This is the basic shape of a +EV scanner.
- **`arb_finder.py`** — scans h2h game lines across every book in
  the response for any pair where combined implied probability is
  under 100%. Computes the optimal stake split for a given bankroll.
  Risk-free profit when an arb exists.
- **`websocket_stream.py`** — subscribes to the live odds WebSocket
  for a sport and prints diff frames as they arrive.

Run any of them after setting `PARLAY_API_KEY`:

```bash
export PARLAY_API_KEY=your_key
cd examples
python ev_scanner.py baseball_mlb player_strikeouts --edge 3.0
python arb_finder.py basketball_nba --bankroll 1000
python websocket_stream.py icehockey_nhl
```

## Devig math

The SDK includes the four standard devig methods so you don't have to
reimplement them:

```python
ParlayAPI.american_to_implied(-110)   # 0.5238
ParlayAPI.american_to_decimal(-110)   # 1.9091
ParlayAPI.decimal_to_american(2.10)   # 110
ParlayAPI.implied_to_american(0.55)   # -122

# Devig with three different methods:
ParlayAPI.devig(-110, -110, method="multiplicative")  # standard
ParlayAPI.devig(-110, -110, method="additive")        # less accurate
ParlayAPI.devig(-1500, +700, method="power")          # better for skewed
```

## Error handling

```python
from parlay_api import (
    ParlayAPI,
    ParlayAPIError,
    InvalidAPIKeyError,
    CreditLimitExceededError,
    RateLimitedError,
    TierGatedError,
)

client = ParlayAPI(api_key="...")
try:
    events = client.odds("basketball_nba")
except CreditLimitExceededError:
    print("hit monthly credit cap")
except RateLimitedError:
    print("slow down, retry in 1s")
except TierGatedError:
    print("upgrade required for this feature")
except InvalidAPIKeyError:
    print("API key revoked or wrong")
except ParlayAPIError as e:
    print("other error:", e)
```

After every successful call the SDK exposes the credit headers via
`client.last_quota`:

```python
client.odds("basketball_nba")
print(client.last_quota.requests_remaining)  # int
```

## Pricing

The free tier includes 1,000 credits/month with no card required.
WebSocket streaming is available on Business tier and up. Current
paid-tier pricing, credits, and rate limits live at
[parlay-api.com/pricing](https://parlay-api.com/pricing).

Sign up at [parlay-api.com](https://parlay-api.com).

## License

MIT. See [`LICENSE`](./LICENSE).

## Bugs and support

[github.com/JacobiusMakes/parlay-api-python/issues](https://github.com/JacobiusMakes/parlay-api-python/issues)
or email [peakpotentialmediaventures@gmail.com](mailto:peakpotentialmediaventures@gmail.com).
