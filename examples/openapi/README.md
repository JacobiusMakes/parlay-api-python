# ParlayAPI private research OpenAPI subset

Two read-only operations for tools that import OpenAPI: list sport identifiers, then request available odds for a selected sport using your own account key. This September 8, 2026 snapshot excludes account, checkout and admin operations.

Start with [current coverage](https://parlay-api.com/coverage) and [API documentation](https://parlay-api.com/docs). [Create your own account](https://parlay-api.com/signup?utm_source=jentic&utm_medium=integration&utm_campaign=private_research) and store its key in your client's credential settings. Prefer the X-API-Key header. Requests consume your account allowance; see [current plans](https://parlay-api.com/pricing). Check one required sport/bookmaker/market combination before selecting a plan for recurring use.

The success schemas describe common documented fields. Optional, nullable fields and extensions are deliberate; schema acceptance does not prove complete coverage, valid timestamps or suitability for a model. Preserve source time separately from retrieval time and keep missing data visible. See PROVENANCE.md for sources and validation limits.

This specification includes no key or live odds payload. Use fetched data privately within your account terms. Publication of this specification does not grant public display, white-label feed or redistribution rights. There is no bet placement operation.

Jentic import and execution require separate validation by that project's maintainers. This file alone does not establish a published catalog integration.
