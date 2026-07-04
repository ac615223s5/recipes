---
name: tandoor-setup
description: One-time environment setup shared by the recipe-importer and grocery-planner skills — Tandoor API credentials (curl/jq + TANDOOR_URL/TANDOOR_TOKEN, persisted in Claude Code's env block), the curl_cffi Python client (Chrome TLS-impersonation, used by grocery-planner's store scripts to beat Akamai), and the Playwright MCP browser automation (headed full Chromium, the fallback for live prices and for reading package-label images). Use when first configuring those skills, or when a Tandoor API call returns 401/403, the env vars are unset, `curl_cffi`/`python` is missing, or the mcp__playwright__browser_* tools are missing.
---

# Tandoor skills — setup

Prerequisites shared by **recipe-importer** and **grocery-planner**. Both talk to a Tandoor instance
over its REST API (via `scripts/tandoor.sh` in each skill). grocery-planner's **preferred** price path
is the `curl_cffi` Python scripts (§3 — headless, beats the grocers' Akamai blocks); the Playwright
MCP browser (§2) is the **fallback** for prices and the primary way recipe-importer reads nutrition
labels off package photos. Get these in place once, then those skills just work.

## 1. Tandoor API access

**Tools:** `curl` and `jq` must be on PATH. (On Windows, install jq with
`winget install jqlang.jq --source winget`; restart the shell so PATH updates.)

**Credentials — two env vars:**
- `TANDOOR_URL` — base URL, no trailing slash (default `http://localhost:8000`).
- `TANDOOR_TOKEN` — an **OAuth2 access token**: Tandoor web UI → Settings → API → Access Tokens.
  - It needs **read + write** scope. A read-only / `mealplan`-scoped token returns **403** on calls —
    if you see 401/403, recreate the token with read+write. Don't guess the token; if it's unset the
    scripts error out — tell the user how to create one.

**Persist them in Claude Code's `env` block** so every session has them automatically — don't rely on
a one-off `export`. Claude Code injects this block into the environment of every Bash call.
- **Preferred: project-local `.claude/settings.local.json`** (this file is local, not committed to git):
  ```json
  { "env": { "TANDOOR_URL": "https://your-tandoor", "TANDOOR_TOKEN": "tda_…" } }
  ```
- Or `~/.claude/settings.json` → `env` to make it available in **all** projects (broader exposure).
- Takes effect on the **next session start**. To rotate the token later, edit this file.
- **Don't** stash the token inside `permissions.allow` strings — it can't be read as a variable there
  and just scatters the secret. Keep it only in `env`.

**Verify:** with the vars set (or in a fresh session), a call should return JSON, not an error:
```bash
curl -fsS -H "Authorization: Bearer $TANDOOR_TOKEN" "$TANDOOR_URL/api/food/?page_size=1"
```
401/403 → token missing or wrong scope. Connection error → wrong URL or server down.

## 2. Playwright MCP (browser automation)

A real browser via the Playwright MCP (`mcp__playwright__browser_*` tools) is the **fallback** for
store prices (when the §3 `curl_cffi` scripts are blocked — e.g. a Walmart Press-&-Hold challenge, or
for Costco) and the **primary** way recipe-importer reads nutrition labels off package photos. Plain
`curl`/`WebFetch` can't reach walmart.ca / T&T (418/403 — Akamai); **full Chromium running headed**
passes their bot defenses (the headless shell does not). If this isn't set up, grocery-planner leans
on §3 (or WebSearch) and recipe-importer can't read labels off package images.

Two pieces must exist:
1. The **MCP server** registered (in `~/.claude.json`), launching headed full Chromium (no `--headless`).
2. **`~/.claude/playwright-mcp-config.json`** with an **`outputDir` outside any git repo** (e.g.
   `~/.cache/playwright-mcp`) — Playwright MCP otherwise litters a `.playwright-mcp/` folder of
   snapshots/logs into the current working directory.

**OS-specific install + register steps (Node.js, browser install, the `cmd /c` wrapper, etc.):**
see **`references/playwright-mcp.md`**.

**Verify (don't assume):** `claude mcp get playwright` shows **Status: ✓ Connected**, and the
`mcp__playwright__browser_*` tools are loaded. The first browser action each session prompts for
permission; a headed Chromium window appears during runs — that's expected and required. If the tools
aren't loaded or the config is missing, set it up (or fall back to WebSearch and say so).

> Note: Playwright MCP saves screenshots to the **current working directory**, not `outputDir` — clean
> up any PNGs you create.

## 3. curl_cffi (Chrome TLS-impersonating HTTP client) — grocery-planner's preferred price path

grocery-planner's store scripts (`scripts/tnt_graphql.py` for T&T, `scripts/walmart_search.py` for
Walmart) use the **`curl_cffi`** Python library with `impersonate="chrome"`. The grocers' 403/418
blocks are just **Akamai fingerprinting the TLS/JA3/HTTP2 stack** — `curl_cffi` sends Chrome's *real*
TLS handshake, so it gets clean JSON **with no browser, no proxy** (T&T GraphQL, Walmart `__NEXT_DATA__`).
This is faster and headless; the §2 browser is only the fallback. A spoofed User-Agent or `requests`
with cookies does **not** work — it must be `curl_cffi`.

**Requires Python 3.10+** (curl_cffi ≥0.14). Install it into the environment whose `python` runs the
scripts:
```bash
uv pip install curl_cffi          # preferred (the scripts' docstrings say this)
# or:  python -m pip install curl_cffi      # plain pip; ships prebuilt wheels (Linux/macOS/Windows)
```
- This repo has a project virtualenv at **`.venv/`** and `python` resolves to it — `curl_cffi` is
  installed there. If `python scripts/tnt_graphql.py …` raises `ModuleNotFoundError: curl_cffi`,
  you're on a different interpreter: activate the venv (`source .venv/bin/activate`) or call the venv
  python directly (`.venv/bin/python scripts/…`), or install curl_cffi into the active one.
- On Windows the wheel installs without a compiler; no extra system libs needed.

**Verify (don't assume):**
```bash
python -c "import curl_cffi; print('curl_cffi', curl_cffi.__version__)"   # prints a version
python scripts/tnt_graphql.py search "milk" --page-size 1                 # from grocery-planner/ → JSON
```
If import works but a request still 403s, update the fingerprint: `impersonate="chrome"` (the alias)
tracks the latest Chrome — pinning an old version (e.g. `chrome110`) can itself be a detection signal.
If curl_cffi can't be installed at all, fall back to the §2 browser recipes (or WebSearch) and say so.
