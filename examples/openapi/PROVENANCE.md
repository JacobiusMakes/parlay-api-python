# Read-only OpenAPI subset, September 8, 2026

Two operations only: GET /v1/sports and GET /v1/sports/{sport_key}/odds. Base projection comes from the already-public OpenAPI document fetched September 8. The original source and transformation receipts stay local; do not publish the full general schema with this contribution.

Success schema provenance uses public SDK revision fb3f76f297c4a74fdce2ec2c48c6fbce3de9493d:

- https://github.com/JacobiusMakes/parlay-api-python/blob/fb3f76f297c4a74fdce2ec2c48c6fbce3de9493d/parlay_api/__init__.py#L211 : sports() documents the six common catalog fields. It calls the compatible v4 route, so this is documentation evidence of common fields, not a v1 runtime capture.
- https://github.com/JacobiusMakes/parlay-api-python/blob/fb3f76f297c4a74fdce2ec2c48c6fbce3de9493d/parlay_api/__init__.py#L242 : odds() documents event fields and nested bookmaker markets/outcomes.
- https://github.com/JacobiusMakes/parlay-api-python/blob/fb3f76f297c4a74fdce2ec2c48c6fbce3de9493d/examples/odds_workspace.py#L150 : public CSV handling reads event and bookmaker clocks, nested market/outcome fields, numeric price and optional point. Line335 builds the exact v1 odds route.

All common response properties are optional and nullable; additional properties are allowed. No unverified field-presence guarantee, enumerated coverage, synthetic examples or actual odds data is supplied. Date-dependent clocks permit string or numeric representation. Parameters, defaults, authentication alternatives and error responses remain as in the public source projection. This artifact is documentation, not a live acceptance test or data redistribution license.

Offline validation passed using the official OpenAPI 3.1 JSON Schema at https://spec.openapis.org/oas/3.1/schema/2022-10-07 with installed jsonschema. All internal references resolve, component schemas pass JSON Schema checks, and route/auth/parameter preservation assertions pass. No Docker or runtime service executed.
