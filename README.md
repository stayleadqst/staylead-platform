# StayLead Platform

This repository contains the new StayLead platform and the Sprint 1 read-only guest Q&A API. It preserves the original repository
identity and starts a modular monolith with two application hosts: a Python/FastAPI API in
`apps/api` and a Next.js web application in `apps/web`. Internal module boundaries are code
organization seams, not separately published libraries or services.

## Architecture

The API package is `staylead_platform`, avoiding a top-level package named `platform` that
would shadow Python's standard library. Its shared platform modules are domain-neutral. The
composition root selects a supported domain profile; Hospitality is scaffolded, while
Electrical Equipment remains a documented future extension. Hospitality-specific schemas,
policies, rooms, stay planning, recommendations and tools have reserved module locations;
the Q&A schemas, fixture mapping and prompts are implemented. Shared platform code must not import Hospitality.

The web app uses Next.js App Router. Shared UI seams live under `src/shared`; Hospitality
landing, content, assets, theme, result views, and registration have domain-owned locations.
`src/composition` selects the Hospitality shell. The source has no language whitelist; future
locale handling must remain open to multilingual input and output.

Each deployment target will select its domain profile, API URL, data resources, and secrets
from deployment configuration. The checked-in `config/targets/hospitality` and `deploy`
trees are placeholders, not deployable infrastructure. `.env.example` files contain
placeholders only. Provider credentials belong on the API side and must never enter browser
configuration.

## Current behavior

Sprint 1 acceptance, supported limits and evidence are recorded in
[the acceptance report](docs/product/SPRINT_1_ACCEPTANCE.md).

- `GET /health` reports that the API process is alive and which compiled-in domain profile
  was selected.
- The web home page is explicitly labeled as a source skeleton. It is not a chat or product demo.
- The PostgreSQL engine factory is lazy; app import and startup do not connect or create schema.
- `POST /v1/guest/sessions` creates a hotel-bound anonymous session from the server bootstrapped
  allowlist; `POST /v1/guest/sessions/{session_id}/messages` sends a bounded FAQ request.
- Guest Q&A uses a scoped M1 fixture retriever followed by one M3 grounded answer call. A bounded
  semantic fact selector adds one call only when lexical coverage is weak, such as a different
  guest/source language. The Foundry Grok adapter is opt-in and configured on the API server.
- PostgreSQL migrations and fixture bootstrap are explicit commands; API startup never creates or
  upgrades schema. Sessions, request idempotency, messages, config and eligible facts persist in
  PostgreSQL.
- The Hospitality composition factory rejects unsupported domain names.

## Not implemented

The Sprint 1 endpoint supports read-only knowledge Q&A only. It does not edit a trip brief or
invoke room allocation, itinerary planning, booking, payment, or staff actions. Real hotel sources,
operator authorization, frontend chat, and deployment remain outside this slice. The checked-in
hospitality fixture is synthetic and must not be presented as live hotel information.
The hospitality fixtures include an authored synthetic knowledge pack with prepared oracle
cases for QA; it is not a production knowledge source or live hotel data
([pack documentation](fixtures/hospitality/knowledge-v1/README.md)). No market or language is
enabled by folder presence alone.

## Local development

API (Python 3.11+):

```sh
cd apps/api
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
python -m staylead_platform.infrastructure.migrations upgrade
python -m staylead_platform.entrypoints.bootstrap_knowledge --fixture-root ../../fixtures/hospitality/knowledge-v1
python -m staylead_platform.entrypoints
```

Set `STAYLEAD_DATABASE_URL` and a private `STAYLEAD_SESSION_SIGNING_SECRET` before running the
migration and bootstrap commands. To enable Foundry Grok, configure
`STAYLEAD_AI_PROVIDER=foundry_grok` with `AZURE_OPENAI_BASE_URL`, `AZURE_OPENAI_API_KEY`, and
`AZURE_OPENAI_MODEL_DEPLOYMENT` in local server-side configuration. The default provider is disabled;
automated tests never fall back to live credentials.

Web (Node.js 20.9+):

```sh
cd apps/web
npm ci
cp .env.example .env.local
npm run dev
```

The API listens on `http://127.0.0.1:8000`; the web app defaults to `http://localhost:3000`.

The optional Sprint 1 live acceptance harness sends a small set of real requests through the
running API and its configured model provider. It is disabled unless explicitly opted in, and
prints answers, evidence, traces, and expected fact IDs without printing session bearer tokens:

```sh
cd apps/api
STAYLEAD_LIVE_EVAL=1 python ../../tools/evals/sprint1_live.py
```

Use this only with a deliberately configured live API. The harness does not run as part of
pytest or any default validation command; its expected fact IDs are evaluation-only and are not
loaded into serving knowledge.

## Local validation

After installing the API development dependencies, run the API smoke and architecture checks
from `apps/api`:

```sh
python -m pytest ../../tests
ruff check --config pyproject.toml src ../../tests
```

PostgreSQL integration tests run only when `STAYLEAD_TEST_DATABASE_URL` points to a dedicated test
database. They use a fake model provider and never make Azure calls.

After installing the web dependencies with `npm ci` from `apps/web`, run the frontend checks there:

```sh
npm run lint
npm run typecheck
npm run build
```

The verified production dependency audit reported no vulnerabilities. The development
dependency audit reported five high-severity findings in the ESLint configuration's transitive
`fast-glob` / `micromatch` / `braces` chain; this remains a known tooling dependency warning.
