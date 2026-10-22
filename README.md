# StayLead Platform

This repository is the new StayLead source skeleton. It preserves the original repository
identity and starts a modular monolith with two application hosts: a Python/FastAPI API in
`apps/api` and a Next.js web application in `apps/web`. Internal module boundaries are code
organization seams, not separately published libraries or services.

## Architecture

The API package is `staylead_platform`, avoiding a top-level package named `platform` that
would shadow Python's standard library. Its shared platform modules are domain-neutral. The
composition root selects a supported domain profile; Hospitality is scaffolded, while
Electrical Equipment remains a documented future extension. Hospitality-specific schemas,
policies, rooms, stay planning, recommendations, tools, and prompts have reserved module
locations only. Shared platform code must not import Hospitality.

The web app uses Next.js App Router. Shared UI seams live under `src/shared`; Hospitality
landing, content, assets, theme, result views, and registration have domain-owned locations.
`src/composition` selects the Hospitality shell. The source has no language whitelist; future
locale handling must remain open to multilingual input and output.

Each deployment target will select its domain profile, API URL, data resources, and secrets
from deployment configuration. The checked-in `config/targets/hospitality` and `deploy`
trees are placeholders, not deployable infrastructure. `.env.example` files contain
placeholders only. Provider credentials belong on the API side and must never enter browser
configuration.

## Current skeleton behavior

- `GET /health` reports that the API process is alive and which compiled-in domain profile
  was selected.
- The web home page is explicitly labeled as a source skeleton. It is not a chat or product demo.
- The PostgreSQL engine factory is lazy; app import and startup do not connect or create schema.
- The Azure OpenAI adapter is an explicit unimplemented boundary. It makes no requests and
  never returns fabricated generated text.
- The Hospitality composition factory rejects unsupported domain names.

## Not implemented

There is no conversation endpoint, AI pipeline, chat/session state, knowledge ingestion or
retrieval, room allocator, itinerary planner, catalog, business policy, authentication, database
schema or migrations, cloud resource, deployment, CI workflow, or working AI provider transport.
The three current tests cover the health response, unsupported domain selection, and the
shared-platform import boundary. Business behavior, end-to-end journeys, and eval cases are
not implemented; the remaining `tests`, `evals`, `fixtures`, `pilot`, and deployment locations
are placeholders. No market or language is enabled by folder presence alone.

## Local development

API (Python 3.11+):

```sh
cd apps/api
python -m venv .venv
. .venv/bin/activate
pip install -e '.[dev]'
cp .env.example .env
python -m staylead_platform.entrypoints
```

Web (Node.js 20.9+):

```sh
cd apps/web
npm ci
cp .env.example .env.local
npm run dev
```

The API listens on `http://127.0.0.1:8000`; the web app defaults to `http://localhost:3000`.

## Local validation

After installing the API development dependencies, run the API smoke and architecture checks
from `apps/api`:

```sh
python -m pytest ../../tests
ruff check --config pyproject.toml src ../../tests
```

After installing the web dependencies with `npm ci` from `apps/web`, run the frontend checks there:

```sh
npm run lint
npm run typecheck
npm run build
```

The verified production dependency audit reported no vulnerabilities. The development
dependency audit reported five high-severity findings in the ESLint configuration's transitive
`fast-glob` / `micromatch` / `braces` chain; this remains a known tooling dependency warning.
