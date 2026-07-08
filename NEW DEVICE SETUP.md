# Setting up on a new machine (from scratch)

A start-to-finish checklist to rebuild the multi-vault Obsidian + Claude Desktop
setup on a fresh PC. Most of this repo is reusable as-is; only two things are
**machine-specific and must be redone on the new PC**:

- your **vault folder paths** (they'll be different on the new machine), and
- your **API keys** (the Local REST API plugin generates *new* keys when installed fresh).

Everything else — the method, the patch, the config shape — is the same.

---

## 0. Install the prerequisites

Install these on the new PC:

- **[Obsidian](https://obsidian.md)** — and your vaults (copy your vault folders over,
  or sync them however you normally do).
- **[Claude Desktop](https://claude.ai/download)**.
- **[uv](https://docs.astral.sh/uv/getting-started/installation/)** — provides `uvx`,
  which runs `mcp-obsidian`. Check with: `uvx --version`.
- **[Python 3.9+](https://www.python.org/downloads/)** — to run the patch script.
  Check with: `python --version`.

## 1. Get this repo onto the new PC

Either:
- Go to the repo page → green **Code** button → **Download ZIP**, and unzip it, **or**
- `git clone https://github.com/SamDP/Obsidian-Claude-Multivault.git`

You now have `README.md`, `patch_mcp_obsidian.py`, etc.

## 2. Set up each vault's REST plugin (per vault)

For **each** vault you want to connect:
1. Open the vault in Obsidian → **Settings → Community plugins → Browse** →
   search **"Local REST API"** and install the one by **Adam Coddington**
   (it displays as **"Local REST API with MCP"**, plugin id
   `obsidian-local-rest-api`) → **Enable** it. Make sure it's this exact plugin —
   its GitHub is <https://github.com/coddingtonbear/obsidian-local-rest-api>.
2. Open its settings and **give it a unique HTTPS port** — e.g. 27124, 27125,
   27126 (each vault must be different; they all default to 27124).
3. **Copy that vault's API key** from the same settings screen. Keep a note of
   which key + which port + which vault.

> Verify a port is live (vault must be open in Obsidian):
> `netstat -ano | findstr "2712"`

## 3. Download mcp-obsidian

Run it once so it's cached, then Ctrl-C:
```
uvx mcp-obsidian
```

## 4. Apply the patch

From inside the repo folder:
```
python patch_mcp_obsidian.py
```
This makes mcp-obsidian honour `OBSIDIAN_PORT`/`OBSIDIAN_HOST` (see
[docs/ROOT_CAUSE.md](docs/ROOT_CAUSE.md) for why this is needed).

## 5. Write your Claude Desktop config

Edit `claude_desktop_config.json` (create it if missing):
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`
- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`

Add one server per vault, each with **its own port and its own new key** — use
[examples/claude_desktop_config.example.json](examples/claude_desktop_config.example.json)
as the template. Back up the file before editing and keep the JSON valid.

> **Windows:** if `uvx` isn't found by Claude Desktop, use the full path to
> `uvx.exe` as `"command"` instead of just `"uvx"`.

## 6. Open the vaults + restart Claude Desktop

- Open **each vault in its own Obsidian window** so every REST server is listening.
- **Fully quit** Claude Desktop (tray → Quit; confirm no `Claude` process is left)
  and relaunch.

## 7. Verify

Ask Claude to list files in each vault, or test a port directly:
```
curl -sk https://127.0.0.1:27125/vault/ -H "Authorization: Bearer <that vault's key>"
```
A JSON file list = working. A 401 = key/port mismatch (see the Troubleshooting
table in [README.md](README.md)).

---

## Fastest path: let Claude Code do it

If you use Claude Desktop's Claude Code on the new PC, paste this to have it walk
you through the whole thing:

> I moved to a new PC and want to set up multiple Obsidian vaults with Claude
> Desktop via mcp-obsidian. Follow the guide in my repo
> https://github.com/SamDP/Obsidian-Claude-Multivault (SETUP.md and
> docs/ROOT_CAUSE.md). Help me: install prerequisites (uv, Python), set a unique
> port for each vault's Local REST API plugin, run patch_mcp_obsidian.py, and
> write the per-vault entries in my claude_desktop_config.json with each vault's
> new API key. My vaults are at: <list your new vault paths here>.
