# Instructions for AI agents

## The purpose

The primary purpose of this project is educational, with no plans for commercial monetization or broad public release. Therefore, please:

- Propose simpler and more efficient approaches to help me learn.
- Explain potential security risks, particularly regarding unexpected billing or cloud costs.

## Learning workflow

- For unfamiliar infrastructure work, explain the purpose of each step,
  the expected result, and how to verify it. Proceed in small steps.
- When I am performing operations to learn, guide me rather than
  performing those operations on my behalf.
- Distinguish observed facts, assumptions, and unverified settings.
  Do not treat a successful UI action or HTTP response as proof that
  the intended configuration change took effect.

## Cloud operations

- Before proposing public access or billable resources, explain who
  can access them, what can incur costs, and how to disable access
  or remove the resources afterward.
- Prefer proportionate safeguards for personal learning. Do not assume
  that production means a broadly public commercial service.
- Keep environment-specific values in the ignored root `.env`.
  Never store credentials there. Use placeholders in public documents.
- Distinguish credentials from resource identifiers, access restrictions
  from service shutdown, and budget alerts from enforced spending limits.

## Implementation guidance

Before making implementation decisions, read [docs/mvp-spec.md](docs/mvp-spec.md).

- Treat `docs/mvp-spec.md` as the source of truth for the first release.
- Do not add routes, current-location search, travel-time calculation, candidate-spot recommendations, PLATEAU, building-height analysis, user accounts, or forecasts beyond today unless the user explicitly requests them.
- Use `docs/requirements.md` only as a record of the broader product vision.
