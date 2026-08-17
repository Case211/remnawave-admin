# Development

## Running locally

```bash
python -m venv .venv
source .venv/bin/activate       # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python -m src.main
```

In `.env` it is enough to point `API_BASE_URL` at a live Remnawave panel and fill in the required fields from [installation](/en/guide/installation#_2-fill-in-env).

The full stack in Docker:

```bash
docker network create remnawave-network
docker compose -f docker-compose.dev.yml up -d
```

## Frontend

```bash
cd web/frontend
npm install
npm run dev
```

React, TypeScript, Vite, Tailwind and shadcn/ui. Tests are Vitest and Testing Library, end-to-end is Playwright.

## Tests

```bash
# panel backend
python -m pytest web/backend/tests -q

# bot
python -m pytest src/tests -q

# frontend
cd web/frontend && npm test -- --run
```

::: warning Run the suites separately
`web/backend/tests` and `src/tests` need separate commands: their environments differ and they interfere with each other in a single run.
:::

## Migrations

Alembic, in `alembic/versions/`. They run automatically at startup — nothing to invoke by hand.

```bash
alembic revision -m "what we are doing"
alembic upgrade head
```

Plugins bring their own migration branches; they are applied along with the main ones.

## Repository layout

A directory-by-directory breakdown is in the [reference](/en/reference/project-layout).

## Conventions

- Code and comments in English, the interface through i18n, both locales at once (`ru` and `en`)
- A new setting is declared in `shared/config_service.py` and appears in the interface by itself
- Verify changes in the Remnawave panel API against the panel sources at the relevant tag, not against the changelog
- The agent version lives in two constants, `node-agent/src/version.py` and `shared/agent_version.py` — they are bumped together
