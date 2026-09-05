# parlay-api

Python 3.9+ SDK for [ParlayAPI](https://parlay-api.com). The default install has
no runtime dependencies and includes a one-request odds-to-CSV starter.

## First response, no key

```bash
python -m pip install --upgrade parlay-api
python -m parlay_api
```

The second command requests the public MLB demo once and prints CSV to your
terminal. It ignores any API key in your environment. Save the response or
choose another supported sport:

```bash
python -m parlay_api --sport americanfootball_nfl > odds.csv
python -m parlay_api --help
```

The demo returns at most the first five US moneyline events, with a shared limit
of 60 requests per hour per IP. Supported demo sports are `baseball_mlb`,
`basketball_nba`, `americanfootball_nfl`, `icehockey_nhl`, `soccer_epl` and
`mma_mixed_martial_arts`. The demo has no market, bookmaker or live filter.
Availability varies by sport, event and source; a sample does not establish full
coverage. An empty response produces a CSV header and a diagnostic.

CSV preserves source prices and source timestamps. Ambiguous duplicate groups
and invalid outcomes are excluded with diagnostics on stderr. Missing timestamps
stay empty; timestamps are not freshness guarantees. The starter makes no
rankings or profit claims, and has no automatic retries, polling or key storage.

## Continue with your own account

[Create your own account](https://parlay-api.com/signup?utm_source=python_sdk&utm_medium=package&utm_campaign=activation_033),
then set `PARLAY_API_KEY` in your terminal. Keep your key private. Explicitly add
`--full` to make one account request and export it for your own analysis:

```bash
python -m parlay_api --full > my-odds.csv
python -m parlay_api --full --markets h2h,spreads,totals --no-include-live > pregame.csv
```

Account requests use US regions and American odds, with `include_live=true`
explicit by default. `--no-include-live` requests pregame data. The same six
sports are supported by the starter, and full mode accepts `h2h`, `spreads` and
`totals`. Requested markets are not a promise that every event or book supplies
them. Your account allowance applies; without `--full`, the command continues
to use the demo even when a key is set.

Use the [Odds workspace](https://parlay-api.com/playground#project) to configure
a request and estimate refresh credits. Current plans, allowances and rate
limits are at [parlay-api.com/pricing](https://parlay-api.com/pricing). Choose
capacity for your intended requests and refresh schedule; this starter does not
start a scheduled job.

## Use the Python client in your project

The library remains available for application code. Pass your key explicitly:

```python
import os
from parlay_api import ParlayAPI

client = ParlayAPI(api_key=os.environ["PARLAY_API_KEY"])
events = client.odds("baseball_mlb", regions="us", markets="h2h")
if not events:
    print("No events returned for this request.")
else:
    for event in events:
        print(event.get("id"), event.get("home_team"), event.get("away_team"))
```

For existing integrations, `ParlayAPI()` also accepts the legacy `PARLAYAPI_KEY`
environment variable. The command-line starter uses `PARLAY_API_KEY` only.

The client includes sports, odds, events, scores, historical odds, player props,
futures, usage and other endpoint methods. Check [current API documentation](https://parlay-api.com/docs)
for parameters, plan requirements and coverage. If migrating from another API,
verify your actual request and response handling against
[the migration guide](https://parlay-api.com/from-toa); endpoint similarities do
not establish identical coverage or behavior.

```python
from parlay_api import InvalidAPIKeyError, ParlayAPIError, RateLimitedError

try:
    events = client.odds("baseball_mlb", markets="h2h")
except InvalidAPIKeyError:
    print("Check the API key for this account.")
except RateLimitedError:
    print("Rate limit reached; review the request schedule.")
except ParlayAPIError as error:
    print(type(error).__name__)
```

After a successful SDK request, `client.last_quota` contains the returned usage
headers. Header fields may be `None` when the service does not provide them.

Optional WebSocket examples require `python -m pip install 'parlay-api[ws]'`.
WebSocket access is Business tier and up; see the current docs before connecting.

## Existing examples

The installed command and the standalone
[odds_workspace.py download](https://raw.githubusercontent.com/JacobiusMakes/parlay-api-python/main/examples/odds_workspace.py)
use the same source file. With no package installation, download that file and
run `python3 odds_workspace.py`; the same flags apply. See
[the source](https://github.com/JacobiusMakes/parlay-api-python/blob/main/examples/odds_workspace.py).

The repository also contains:

- [ev_scanner.py](https://github.com/JacobiusMakes/parlay-api-python/blob/main/examples/ev_scanner.py): illustrates a chosen fair-price baseline and an edge calculation. Results depend on assumptions and available inputs.
- [arb_finder.py](https://github.com/JacobiusMakes/parlay-api-python/blob/main/examples/arb_finder.py): illustrates implied-probability and stake calculations. Quotes and execution can change; a computed opportunity does not guarantee profit.
- [websocket_stream.py](https://github.com/JacobiusMakes/parlay-api-python/blob/main/examples/websocket_stream.py): illustrates consuming a WebSocket stream with your own account.

These additional files are repository examples. Download or clone them separately;
`pip install parlay-api` does not create an `examples` directory.

## License and data use

The software is MIT licensed; see
[LICENSE](https://github.com/JacobiusMakes/parlay-api-python/blob/main/LICENSE).
Installing or sharing this code grants no data distribution rights. API data use
is governed by the [applicable Terms](https://parlay-api.com/terms) and any written
agreement. This starter is intended for personal analysis and does not offer a
shared community feed. These tool defaults do not amend existing customer
agreements. Each person running it should use their own account and key.

## Development and support

From a checkout, run the standalone offline tests with
`python -m unittest discover -s examples -p 'test_odds_workspace.py'`.
After installing a built wheel into a clean environment, run
`python /absolute/path/to/tests/test_installed_package.py` from outside the
checkout to verify the installed entry point and replay the same fixture tests.
All test requests are mocked.

Report bugs at [GitHub issues](https://github.com/JacobiusMakes/parlay-api-python/issues)
or contact [support](mailto:peakpotentialmediaventures@gmail.com).
