# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Tandoor Recipes is a self-hosted recipe manager. It is a **Django 5.2 backend** (the `cookbook` app) serving a **Vue 3 + Vuetify frontend** (`vue3/`). The frontend is built with Vite and served by Django via `django-vite`; the Vue app talks to the backend through a Django REST Framework API whose TypeScript client is auto-generated from the OpenAPI schema.

## Common Commands

All Python commands assume an activated virtualenv. Frontend commands run from `vue3/`.

> First-time local setup is captured as runnable cells in `run-python.bashbook` and `run-vue.bashbook` (VSCode "bashbook" notebooks). They use **uv** for the backend (`uv venv` → `source .venv/bin/activate` → `uv pip install -r requirements.txt` → `makemigrations`/`migrate` → `DEBUG=1 python manage.py runserver`) and `yarn install` → `yarn dev` for the frontend. Start `yarn dev` **before** `runserver`.

### Backend (Django)
```bash
python manage.py migrate                  # apply migrations
python manage.py runserver                # dev server (http://127.0.0.1:8000)
python manage.py collectstatic            # collect static incl. built vue3 bundle
python manage.py seed_basic_data          # seed dev data (cookbook/management/commands/)
python manage.py rebuildindex             # rebuild full-text search index
```

### Frontend (Vue 3)
```bash
yarn install
yarn dev      # vite dev server on :5173 with hot reload — MUST be started before runserver for hot reload
yarn build    # builds into ../cookbook/static/vue3/ (run + restart django if not using yarn dev)
```

### Tests
```bash
pytest                                    # full suite (config in pytest.ini, uses recipes.test_settings)
pytest cookbook/tests/api/test_api_recipe.py            # single file
pytest cookbook/tests/api/test_api_recipe.py::test_x    # single test
pytest --no-cov -n 0 <path>               # disable coverage + xdist (needed for debugging / breakpoints)
```
`pytest.ini` enables coverage and `pytest-xdist` (`-n auto`) by default. Tests live in `cookbook/tests/` and use `pytest-factoryboy` factories (`cookbook/tests/factories/`) and fixtures in `conftest.py`.

### Linting & Formatting
Python uses **flake8 + yapf + isort** (all configured for `max-line-length = 179`); Vue/TS uses **prettier** (`printWidth: 179`, no semicolons, 2-space tabs).
```bash
flake8 file.py --ignore=E501 | isort -q file.py | yapf -i file.py
prettier --write file.vue
```
Note: yapf puts each list element on its own line when a list has a trailing comma.

### API Client Generation
When changing API ViewSets/serializers, regenerate the TS client. Requires Java + `@openapitools/openapi-generator-cli`. With the django server running on :8000:
```bash
python generate_api_client.py             # writes to vue3/src/openapi/ from the live /openapi/ schema
```

## Architecture

### Multi-tenancy via Spaces (critical)
Almost all data is scoped to a `Space` (`cookbook/models.py`). This is enforced with **django-scopes**: `cookbook/helper/scope_middleware.py` (`ScopeMiddleware`) activates the request's space scope, and querysets on scoped models will **raise `ScopeError` if accessed without an active scope**. When writing tests or management commands that touch scoped models, wrap access in `with scopes_disabled():` or `with scope(space=...):`. A user can belong to multiple spaces via `UserSpace`, and spaces contain `Household`s.

### Permission model
Most models mix in `PermissionModelMixin` (`models.py`); permission checks live in `cookbook/helper/permission_helper.py` (decorators like `group_required`, `CustomIsOwner`/`CustomIsShared` DRF permission classes, and `has_group_permission`). Hierarchical models (`Keyword`, `Food`) extend `TreeModel` (django-treebeard `MP_Node`); `Unit`, `Food`, `SupermarketCategory` use `MergeModelMixin` for merge/rename operations.

### Backend layout (`cookbook/`)
- `models.py` — all DB models (single large file).
- `serializer.py` — DRF serializers; uses `drf-writable-nested` for nested writes (e.g. Recipe → Steps → Ingredients).
- `views/api.py` — DRF ViewSets (the main API surface, ~3.5k lines); `views/views.py` — server-rendered/auth pages; `views/import_export.py`, `views/telegram.py`.
- `urls.py` — registers ViewSets on a DRF router; OpenAPI schema served at `/openapi/` via drf-spectacular.
- `helper/` — business logic: `recipe_search.py` (Postgres full-text + trigram search), `ingredient_parser.py` / `cooklang_parser.py`, `recipe_url_import.py` (recipe-scrapers website import), `ai_helper.py` (LLM features via litellm), `shopping_helper.py`, `automation_helper.py`, image/property/unit-conversion helpers.
- `integration/` — importers/exporters for other recipe managers (Chowdown, Cookmate, Gourmet, etc.), each subclassing `integration/integration.py`.
- `connectors/` — outbound integrations (e.g. Home Assistant) via `connector_manager.py`.
- `provider/` — sync providers (Dropbox, Nextcloud, local).
- `management/commands/` — CLI commands.

### Frontend layout (`vue3/src/`)
- `apps/` — entry points; the main build input is `apps/tandoor/main.ts` (see `vite.config.ts`). Plugins under `src/plugins/*/plugin.ts` can register additional build inputs.
- `openapi/` — **generated** API client (do not hand-edit; regenerate via `generate_api_client.py`).
- `pages/`, `components/`, `composables/`, `stores/` (Pinia), `utils/`, `types/`.
- `locales/*.json` — frontend translations; `vite.config.ts` computes per-locale translation coverage at build time (`virtual:locale-coverage`) and hides locales below `LOCALE_MIN_COVERAGE` (25%). Backend translations are gettext `.po` files under `cookbook/locale/`.
- `service-worker.ts` — PWA service worker (vite-plugin-pwa, injectManifest strategy).

### Settings & config
`recipes/settings.py` is heavily env-var driven (see `.env.template` and the full list in the docs). `recipes/test_settings.py` is used by pytest. Most behavior limits are `SPACE_*` / per-space settings. Auth uses django-allauth (incl. MFA, social, LDAP, SAML) and django-oauth-toolkit (scopes: read/write/bookmarklet/mealplan).

## Plugins
Optional Python plugins live in `recipes/plugins/<name>/` and are linked by running `python plugin.py` (also builds the frontend); set `PLUGINS_BUILD=1` to trigger this in the Docker entrypoint (`boot.sh`).

## Contribution Notes
- Functional changes require pytest tests (`docs/contribute/guidelines.md`).
- Contributing requires signing the CLA. Larger features should be discussed (technical description) before a PR.
- Full docs: https://docs.tandoor.dev/ (built from `docs/` via mkdocs; `mkdocs serve`).
