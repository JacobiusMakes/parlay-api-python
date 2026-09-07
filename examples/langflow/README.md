# Odds Sample Audit for Langflow

A four-component workflow that inspects a fictional odds response before it is used elsewhere. It makes one GET to a pinned GitHub fixture, checks market completeness and source timestamp presence, and prints a structured report. No API key, LLM, or credits are required.

Import **Odds Sample Audit.json** into Langflow. The built-in JSON Operations component uses JQ Expression, which requires `jq` in your Langflow Python environment. Run the final Chat Output component. The fixture intentionally produces:

- 1 complete market with both team outcomes.
- 2 incomplete or ambiguous markets, including duplicate market groups.
- 1 missing source timestamp.

The JSON Operations query is visible in the editor. It preserves the supplied prices and timestamps. A timestamp being present does not mean it is valid or current. The outcome lists on incomplete groups are diagnostic input, not usable quotes. This flow calculates no betting edge, recommendations, or profit.

Chat message storage and response file saving are disabled. Langflow may retain other execution logs according to the instance's configuration. Keep real data and logs private if you adapt this workflow.

The fixture contains fictional teams, bookmakers, prices, and dates. It is MIT-licensed teaching data, not a sample of current ParlayAPI coverage. For a separate own-key workflow, see the [ParlayAPI Python SDK](https://github.com/JacobiusMakes/parlay-api-python). Software licensing does not include API data redistribution rights or amend customer agreements.

Validation status: the flow uses published Langflow 1.12.0 built-in component definitions. Fifteen offline query and graph checks pass. Native Langflow import, execution, and editor screenshot validation are pending the proposed isolated CI job. Do not treat this status as a native compatibility claim.

The embedded built-in component definitions come from [Langflow v1.12.0](https://github.com/langflow-ai/langflow/tree/v1.12.0), under its MIT license included in `UPSTREAM-LICENSE.txt`. The fixture URL is pinned to its source commit.
