# Obsidian + Claude: Multi-Vault Setup

Connect **multiple Obsidian vaults** to **Claude Desktop** at the same time, using
the REST-API-based [`mcp-obsidian`](https://github.com/MarkusPfundstein/mcp-obsidian)
MCP server — with Obsidian free to stay open.

If you've tried this and hit **persistent `401 Unauthorized` / `Error 40101:
Authorization required`** on your second vault even though the key is correct,
this repo explains exactly why and fixes it.

---

## TL;DR — why a second vault fails out of the box

`mcp-obsidian` reads your API key but **ignores `OBSIDIAN_PORT` and
`OBSIDIAN_HOST`**. Every vault's server process connects to the hardcoded default
`https://127.0.0.1:27124`. So your second vault sends *its* key to the *first*
vault's REST server, which rejects the unknown key with a 401.

It looks like an auth problem. It's actually a **port-routing bug**. The key was
never wrong — it was being delivered to the wrong server. Full write-up in
[`docs/ROOT_CAUSE.md`](docs/ROOT_CAUSE.md).

Two things are needed to run multiple vaults:

1. Give **each vault's Local REST API plugin a unique port** (they all default to 27124 too).
2. **Patch `mcp-obsidian`** so it actually honours the port you configure — run
   [`patch_mcp_obsidian.py`](patch_mcp_obsidian.py).

---

## Prerequisites

- **Obsidian** with the **"Local REST API"** community plugin installed and enabled
  in *each* vault you want to connect.
- **Claude Desktop** (this uses `claude_desktop_config.json`; local MCP servers do
  **not** work in the claude.ai web app or mobile).
- **[uv](https://docs.astral.sh/uv/)** installed (provides `uvx`), which runs
  `mcp-obsidian`. Verify with `uvx --version`.
- **Python 3.9+** on PATH (to run the patch script).

---

## Setup

Example below uses three vaults on ports **27124 / 27125 / 27126**. Use as many
as you like — just keep each port unique.

### 1. Enable the Local REST API plugin in every vault

In each vault: **Settings → Community plugins → Browse → "Local REST API" →
Install → Enable**. Then open its settings and **copy the API key** — you'll need
one per vault.

### 2. Give each vault a unique port

In each vault's **Local REST API** settings, set a different HTTPS port:

| Vault    | Port  |
| -------- | ----- |
| Vault A  | 27124 |
| Vault B  | 27125 |
| Vault C  | 27126 |

(Equivalently, edit `port` in each vault's
`.obsidian/plugins/obsidian-local-rest-api/data.json`. If you edit the file
directly, reload that vault so the plugin re-reads it.)

> **Verify each port is actually listening** (each vault must be *open* in
> Obsidian for its server to run):
> - Windows: `netstat -ano | findstr "2712"`
> - macOS/Linux: `lsof -iTCP -sTCP:LISTEN | grep 2712`

### 3. Patch mcp-obsidian

Run `mcp-obsidian` once so it's downloaded (`uvx mcp-obsidian` — Ctrl-C after it
prints that it's running), then:

```bash
python patch_mcp_obsidian.py
```

It finds every installed copy, backs each up as `tools.py.bak`, and makes them
honour `OBSIDIAN_HOST` / `OBSIDIAN_PORT` / `OBSIDIAN_PROTOCOL`. Safe to re-run.

### 4. Add one server entry per vault to Claude Desktop

Edit `claude_desktop_config.json` and add a server per vault, each with its **own
port and its own key**. See [`examples/claude_desktop_config.example.json`](examples/claude_desktop_config.example.json).

```jsonc
"mcp-obsidian-vault-a": {
  "command": "uvx",
  "args": ["mcp-obsidian"],
  "env": {
    "OBSIDIAN_API_KEY": "<vault A key>",
    "OBSIDIAN_HOST": "127.0.0.1",
    "OBSIDIAN_PORT": "27124"
  }
},
"mcp-obsidian-vault-b": {
  "command": "uvx",
  "args": ["mcp-obsidian"],
  "env": {
    "OBSIDIAN_API_KEY": "<vault B key>",
    "OBSIDIAN_HOST": "127.0.0.1",
    "OBSIDIAN_PORT": "27125"
  }
}
```

**Config file location:**
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

> **Windows note:** if `uvx` isn't found, use the absolute path to `uvx.exe` as
> `"command"`, e.g. `"C:\\Users\\<you>\\AppData\\Roaming\\Python\\Python3xx\\Scripts\\uvx.exe"`.
> Back up the config before editing, and keep the JSON valid.

### 5. Open the vaults and restart Claude Desktop

- Open **each vault in its own Obsidian window** (vault switcher → *Open in new
  window*), so every REST server is listening on its port at the same time.
- **Fully quit** Claude Desktop (tray → Quit; confirm no `Claude` process
  remains) and relaunch, so it re-reads the config.

### 6. Verify

Ask Claude to list files in each vault, or test a port directly:

```bash
curl -sk https://127.0.0.1:27125/vault/ -H "Authorization: Bearer <vault B key>"
```

A JSON file list = success. A `401` = the key doesn't match the server on that
port (see Troubleshooting).

---

## Troubleshooting

| Symptom | Likely cause | Fix |
| --- | --- | --- |
| `401 / Error 40101` on some vaults | mcp-obsidian ignoring the port → key sent to wrong vault's server | Run `patch_mcp_obsidian.py`, restart Claude Desktop |
| `401` even after patching | Two config entries share a port, or a key is pasted to the wrong entry | Ensure each entry has a unique port + its matching key |
| Read timeout / connection refused | That vault isn't open in Obsidian, or nothing is listening on the port | Open the vault; confirm the port with `netstat`/`lsof` |
| Only one vault ever works | All plugins still on default port 27124 | Give each vault a unique port (Step 2) |
| Worked, then broke after an update | `uv` re-extracted a fresh, unpatched copy | Re-run `patch_mcp_obsidian.py` |
| Tools appear but every call fails | `tools/list` is local; only real calls hit Obsidian | It's a connection issue — check port/key/patch |

---

## How it works / root cause

The `401` is a **port-routing bug**, not an auth bug, and it is **not** an
HTTP-vs-HTTPS mismatch (the package always uses HTTPS). Each Obsidian vault runs
its own REST server on its own port and accepts only its own key; the key says
*"am I allowed?"* while the port decides *"which server am I talking to?"*.
Because the package hardcoded the port, every key was mailed to the same address.
Full analysis: [`docs/ROOT_CAUSE.md`](docs/ROOT_CAUSE.md).

---

## Notes & caveats

- The patch edits files in `uv`'s cache. `uv cache clean` or a package update can
  replace them — just re-run the patch script (it's idempotent).
- Each vault must be **open in Obsidian** for its REST server to run. This is the
  trade-off of the REST-API approach; in exchange, Obsidian can stay open while
  you work with Claude.
- Consider [contributing the fix upstream](https://github.com/MarkusPfundstein/mcp-obsidian)
  so patching is eventually unnecessary.

## License

[MIT](LICENSE)
