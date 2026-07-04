# Root Cause Analysis: the multi-vault `401` bug

A precise, evidence-based account of why connecting a second Obsidian vault to
Claude Desktop via `mcp-obsidian` fails with `401 Unauthorized`, and how it was
fixed. Written to be accurate rather than tidy.

## Symptoms

- Vault 1 works perfectly.
- Vault 2 returns `Error 40101: Authorization required` (HTTP 401) on every tool
  call, even though:
  - the server process starts, connects, and lists tools fine;
  - the API key is correct (verified clean via hex dump — no hidden characters);
  - there are no duplicate/stale processes, no leaked system env vars, no
    obvious host/port collisions in the config.

## The wrong theory (HTTP vs HTTPS) — and why it's wrong

A tempting hypothesis is that requests to vault 2 went out over `http://` while
Obsidian's plugin only accepts `https://`, producing a 401.

This is **disproven by the package source**. In `mcp_obsidian/obsidian.py`:

```python
class Obsidian():
    def __init__(self, api_key, protocol='https', host="127.0.0.1",
                 port=27124, verify_ssl=False):
```

- `protocol` defaults to `'https'` and is never overridden anywhere → no `http://`
  request is ever made.
- `verify_ssl=False` → the self-signed certificate is accepted, so TLS/cert
  issues aren't in play either.

Also decisive: a protocol mismatch (HTTP → an HTTPS-only server) yields a
transport-level failure — a connection reset, an empty reply, or a "Bad Request"
— **not** a clean `401` carrying Obsidian's JSON error body
(`Error 40101: Authorization required`). Receiving that structured 401 *proves*
the request reached Obsidian's REST server over the correct protocol, was parsed,
and was rejected purely on the bearer token. That is an **authenticated
rejection**, which rules out both a protocol mismatch and a cert problem.

## The actual root cause: the port is ignored

Every tool in `mcp_obsidian/tools.py` constructs the client like this:

```python
api = obsidian.Obsidian(api_key=api_key)   # no host=, no port=
```

`OBSIDIAN_HOST` and `OBSIDIAN_PORT` appear **nowhere** in the package — only
`OBSIDIAN_API_KEY` is read. So those env vars in your Claude Desktop config are
**dead config**: silently ignored. Combined with the defaults above, **every
vault's process connects to `https://127.0.0.1:27124`**, regardless of the port
you set.

### Why that produces a 401

Each Obsidian vault runs its **own** REST server, and each server accepts **only
its own** API key.

| Vault | Key (configured) | Port (configured) | Port actually used |
| ----- | ---------------- | ----------------- | ------------------ |
| 1 | key-1 | 27124 | **27124** |
| 2 | key-2 | 27125 | **27124** ← ignored |

- Vault 1 process → sends `key-1` to `:27124` → matches vault 1's server → **200 OK**
- Vault 2 process → sends `key-2` to `:27124` (vault 1's server) → key not
  recognised → **401 Unauthorized**

The key was never wrong. It was being **delivered to the wrong server**. A key
answers *"am I allowed to talk to this server?"*; the port decides *"which server
am I talking to?"*. The bug corrupted only the second question.

### A second, overlapping default made it worse

The **Local REST API plugin** *also* defaults to port **27124**. So even if you
correctly set `OBSIDIAN_PORT=27125`, two problems stacked:

1. the client ignored the port (always dialing 27124), **and**
2. multiple open vaults all tried to bind 27124, so only one server could exist
   there anyway.

Two independent "everything defaults to 27124" bugs — one client-side, one
server-side — masking each other. That's why it was so resistant to debugging.

## Explaining the confusing observations

- **`curl` "worked" but the MCP process didn't.** When `curl` succeeded it was
  because the correct port was typed into the URL by hand. `curl` bypassed the
  package entirely. The package couldn't be told which port to use, so it always
  hit 27124. "curl to :27125 works, the server process fails" is the exact
  fingerprint of a client ignoring the configured port.
- **`tools/list` succeeded but `tools/call` failed.** `tools/list` is answered
  entirely by the local Python MCP process from its static tool registry — it
  never contacts Obsidian. Only `tools/call` issues a real HTTP request to
  Obsidian's REST API, so the misrouting was invisible until an actual call.
- **"Process started, connected, listed tools."** All of that is local MCP
  handshake; none of it validates the port or key against Obsidian. The first
  thing that ever touches Obsidian is a tool call.

## The fix

Patch `mcp_obsidian/tools.py` to read the env vars and pass them through:

```python
api_key = os.getenv("OBSIDIAN_API_KEY", "")
obsidian_protocol = os.getenv("OBSIDIAN_PROTOCOL", "https")
obsidian_host = os.getenv("OBSIDIAN_HOST", "127.0.0.1")
obsidian_port = int(os.getenv("OBSIDIAN_PORT", "27124"))
...
api = obsidian.Obsidian(api_key=api_key, protocol=obsidian_protocol,
                        host=obsidian_host, port=obsidian_port)
```

Three things together produced a fully working multi-vault setup:

1. **Patch the package** (the decisive root-cause fix) so `OBSIDIAN_PORT` means
   something — see [`../patch_mcp_obsidian.py`](../patch_mcp_obsidian.py).
2. **Assign each vault's plugin a unique port** (e.g. 27124/27125/27126) so every
   REST server can bind and run simultaneously.
3. **Enable the plugin in every vault** (in one case it was installed but switched
   off in `community-plugins.json`).

Verified by driving the patched server against port 27125 and getting the correct
vault's file list, then by all vaults responding correctly at once with Obsidian
open.

## Confidence / provenance

- The **package-ignores-port bug is confirmed from source** and by **direct
  reproduction**: with vaults on 27124/27125/27126 and distinct keys, only the
  27124 vault worked (identical `Error 40101`), and patching the port handling
  fixed all of them.
- The original two-vault failure itself was not captured in live traffic logs;
  its explanation is reconstructed from (a) the confirmed source bug, (b) the
  saved original config (vault 2 on 27125 with a distinct key), and (c) the
  in-session reproduction. Together these make the conclusion definitive: the
  `401` was a **port-routing bug that surfaced as an auth error**, not an
  HTTP/HTTPS mismatch and not a bad key.
