# ParlayAPI private research in Bruno

Open this folder as a collection in [Bruno](https://www.usebruno.com/). Start with **01 Public discovery / 03 MLB moneyline demo**, then click **Send**. No key or account is required for that request. It returns up to five MLB events with US moneyline data; an empty response is possible.

This is a small native Bruno collection with a visible sport selector, local environment handling, guards for private requests and response assertions. The broader [Postman collection](https://parlay-api.com/postman) remains available for other endpoints and clients.

| Folder | Requests | Key needed |
| --- | --- | --- |
| Public discovery | Current plans, sports catalog, MLB moneyline demo | No |
| Private requests | Selected-sport moneyline odds, your usage and allowance | Your own key and explicit opt-in |

## Make one private request

1. Save your own API key. Review **Current plans** and [current limits](https://parlay-api.com/pricing); account allowances apply.
2. Copy `.env.example` to `.env` in this collection folder. The latter is ignored by Git. Put your own key after `PARLAY_API_KEY=` and change `PARLAYAPI_ENABLE_PRIVATE_REQUESTS=false` to `PARLAYAPI_ENABLE_PRIVATE_REQUESTS=true`. Keep that file local. Do not put a key in a request URL, shared environment or commit.
3. Select the **Personal** environment. Its visible `sport_key` variable is the one place to choose a sport, starting with `baseball_mlb`. Copy another sport key from **Sports catalog** if needed. Open **02 Private requests / 01 Sport moneyline with my key** and click **Send**. The remaining parameters are fixed and visible: one US moneyline market, American prices, ISO dates and `include_live=true`.
4. Open **My usage and allowance** and click **Send** to inspect your private account response. Return the opt-in flag to `false` when finished.

Private requests are blocked in collection runs even when enabled. Each private request requires the app's single-request mode. This intentionally leaves the CLI and Run Collection for public discovery only. There is no polling, retry script, signup, email or billing action. Redirect following is disabled and each request has a 30-second timeout. The guard permits only the documented GET routes on the canonical HTTPS origin, with a validated sport slug and fixed query parameters and injects the key after the private checks pass.

If a request returns 403, check whether the public request is being refused or your private key/access needs attention. For 429, inspect the response and retry only when you choose after the indicated wait. An empty event array is valid. A malformed wrapper fails the response assertion. No script stores or logs a response, price or key. Bruno still displays responses and request details in its local UI; keep private tabs, history and exports private.

## Data and software

This collection contains request definitions and test code, with no captured odds or customer responses. Source prices and timestamps are shown as returned; this collection does not calculate rankings or infer freshness. Availability varies by event, market and source.

The collection code is MIT licensed. API data redistribution rights are not included. [API Terms](https://parlay-api.com/terms) and any written agreement govern data use. Each person uses their own account, never one community feed key.

## Validation

The published Bruno parser, actual request runtime class and synthetic request tests validate the local artifact. No real account request, key, Bruno GUI import or paid action was used in that validation.
