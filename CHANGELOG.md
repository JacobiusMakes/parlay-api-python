# Changelog

## 0.3.3 - 2026-09-05

- Bundle the existing standalone odds workspace starter in the installed package.
  Run `python -m parlay_api` for one no-key US moneyline demo request, or explicitly
  use `--full` with your own `PARLAY_API_KEY` for an account request.
- Keep `examples/odds_workspace.py` as the single implementation and working
  standalone download. No new dependency, polling loop, retry or key storage.
- Lead the README with the first response and own-key transition. Replace broad
  coverage, comparison and profit claims with response limits and current links.
- Preserve source timestamps, duplicate-group exclusions, CSV escaping and
  response validation in both entry points. Add installed-package parity checks.


## 0.3.2 (2026-08-25)

### Changed

- README: corrected source count to "45+ sportsbooks & sources"
  (the "22 sources" figure was stale).
- README: pricing table replaced with a link to
  [parlay-api.com/pricing](https://parlay-api.com/pricing) so listed
  prices can't drift out of date. Free tier (1,000 credits/month, no
  card) and Business+ WebSocket availability stated inline.
- Package classifier: Development Status 4 - Beta upgraded to
  5 - Production/Stable.
- Repo synced with the code published to PyPI as 0.3.0/0.3.1 (those
  releases were published without a matching repo push; see below).

## 0.3.0 / 0.3.1 (published to PyPI without a repo push)

### Added

- Keyless client: `ParlayAPI()` now works without an API key for
  keyless endpoints (sports, status, live board), with fallback to
  the `PARLAYAPI_KEY` environment variable. Keyed calls raise
  `InvalidAPIKeyError` at call time.
- POST support in the request layer (`method`, `json_body`).
- Value-hunting methods: `middles()`, `verdict()`,
  `parlay_verdict()`, `best_bets()`, `set_bettable_books()`,
  `bettable_books()`.

## 0.2.0 (2026-05-04)

Major method coverage expansion. v0.1.0 shipped with 9 endpoint methods;
v0.2.0 brings the SDK to 23 endpoint methods (+ 9 math/devig helpers).

### Added

- `bookmakers(all=False)`: bookmaker registry with status (active /
  merged / decommissioned / not_yet_integrated).
- `participants(sport_key)`: teams or players that have appeared in
  events for a sport.
- `live(sport_key, regions, markets, bookmakers, odds_format)`: in-play
  events only.
- `compare(sport_key, markets, odds_format)`: side-by-side line
  comparison across all books per event with best-line highlight.
- `arbitrage(sport_key, min_profit)`: pre-computed cross-book
  arbitrage opportunities.
- `ev(sport_key, min_edge)`: pre-computed +EV opportunities vs no-vig
  consensus.
- `consensus(sport_key, markets, odds_format)`: no-vig consensus fair
  odds across all books.
- `closing_lines(sport_key)`: most recent closing prices for completed
  events.
- `historical_closing_odds(sport_key, markets, ...)`: historical
  closing lines for both game-line markets and player props. Mix
  `markets="h2h,player_strikeouts"` freely; game lines route to
  historical_odds, props to prop_closing_lines.
- `line_movement(sport_key, event_id, market_key, ...)`: time-series
  price history for one market.
- `prop_coverage(sport_key)`: which bookmakers cover which prop
  market types per sport.
- `historical_coverage()`: archive stats including per-sport coverage
  map.
- `prediction_markets(sport_key)`: Kalshi + Polymarket prices
  normalized to the same schema as sportsbook responses.
- `exchange_markets(sport_key)`: Novig + ProphetX exchange prices
  including lay sides.
- `inplay_arbs()`: cross-source in-play arbitrage firehose.
- `stats()`: live API throughput stats (public, no auth).
- `health()`: liveness probe (public, no auth).

### Changed

- `pyproject.toml` description rewritten to reflect the wider scope
  (props, prediction markets, exchanges, historical archive).

### Migration from 0.1.0

No breaking changes. Existing code keeps working. New methods are
additive.

## 0.1.0 (2026-04-26)

Initial release. Shipped:

- `sports`, `odds`, `events`, `scores`, `historical_odds`, `props`,
  `prop_markets`, `futures`, `usage` REST methods.
- `websocket_url` helper.
- Devig math helpers: `american_to_implied`, `american_to_decimal`,
  `decimal_to_american`, `implied_to_american`, `devig` (multiplicative,
  additive, power), `edge`.
- Error class hierarchy: `ParlayAPIError`, `InvalidAPIKeyError`,
  `CreditLimitExceededError`, `RateLimitedError`, `TierGatedError`.
- `Quota` dataclass for tracking `x-requests-*` headers.
