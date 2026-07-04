# Playwright MCP — install & register

Detailed steps for the two pieces described in `SKILL.md` §2: the MCP server registered to launch
**headed full Chromium** (the headless shell fails the grocers' Akamai bot checks), and
`~/.claude/playwright-mcp-config.json` with an `outputDir` outside any git repo.

## Windows (verified 2026-06-26, native Windows Claude Code build)

Prereq: **Node.js** (provides `npx`). If `node -v` fails:
```bash
winget install OpenJS.NodeJS.LTS --source winget --accept-source-agreements --accept-package-agreements
```
After install, restart Claude Code so it inherits the updated system PATH (the running process won't
see `npx` until then). Node lands at `C:\Program Files\nodejs`.

1. Config file `C:\Users\<user>\.claude\playwright-mcp-config.json` (forward slashes in `outputDir`):
   ```json
   {
     "browser": {
       "browserName": "chromium",
       "isolated": false,
       "launchOptions": { "headless": false }
     },
     "outputDir": "C:/Users/<user>/.cache/playwright-mcp"
   }
   ```
   Create the dir: `mkdir -p ~/.cache/playwright-mcp`.

2. Register the MCP server (launch via `cmd /c` so `npx` resolves on Windows):
   ```bash
   MSYS_NO_PATHCONV=1 claude mcp add playwright --scope user -- \
     cmd /c npx -y @playwright/mcp@latest --browser chromium \
     --config "C:\Users\<user>\.claude\playwright-mcp-config.json"
   ```
   `MSYS_NO_PATHCONV=1` is required when running from Git Bash, or `/c` gets mangled to `C:/`.
   Verify with `claude mcp get playwright` — Args should read `/c npx -y @playwright/mcp@latest ...`.

3. Install **full Chromium** (the headless shell alone fails the bot checks):
   ```bash
   npx -y playwright install chromium
   ```
   Lands in `C:\Users\<user>\AppData\Local\ms-playwright\chromium-<n>` (Chrome for Testing).

4. Restart Claude Code. Confirm `claude mcp get playwright` shows **Status: ✓ Connected** and the
   `mcp__playwright__browser_*` tools are available. First browser action prompts for permission;
   a headed Chromium window appears during runs — that's expected and required.

No `DISPLAY` is needed on Windows.

## Linux

Same config json as above (Linux paths, e.g. `outputDir: "/home/<user>/.cache/playwright-mcp"`).
Register the MCP server in `~/.claude.json` → `mcpServers.playwright` with:
`args: ["-y","@playwright/mcp@latest","--browser","chromium","--config","/home/<user>/.claude/playwright-mcp-config.json"]`
(NO `--headless`) and `env: {"DISPLAY": ":0"}` (no `cmd /c` wrapper). Install browsers without root:
`npx -y playwright install chromium` (and `npx -y @playwright/mcp@latest install-browser chrome-for-testing`
if prompted). A headed browser window appears during runs — required to beat the bot defenses.

## Notes
- Config changes take effect on the next MCP server restart (i.e. next Claude Code session).
- Tested 2026: with `--headless` (chrome-headless-shell) Akamai returns "Forbidden" (Walmart) /
  "Access Denied" (T&T); full Chromium headed passes both.
- Docs: https://playwright.dev/docs/getting-started-mcp and https://code.claude.com/docs/en/mcp.md
