# Changelog

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
