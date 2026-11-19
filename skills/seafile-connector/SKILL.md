---
name: seafile-connector
description: >-
  Access a Seafile server through its REST API with portable, stdlib-only
  scripts: list libraries, browse directories, get file details, download
  files, search (account token), list trash, and build filemap.json
  inventories with change detection (mtime/size diff). Optional upload via
  upload link. Use this skill wherever a Mistral Studio/Work HTTP connector
  is not available (e.g. Work Web chats, whose code interpreter has no
  network) or for scripted sync/filemap logic in any networked environment
  (Vibe Code, Studio agent sandbox with network enabled).
---

# seafile-connector

Portable Seafile access via `scripts/seafile_api.py` (Python 3.10+, standard
library only — no pip install needed). All Mistral-specific setup (HTTP
connector registration in Studio/Work) lives in the repo under
`adapters/mistral/` and is NOT part of this skill folder.

## Prerequisites

- Network access to the Seafile server. The server must be reachable over
  **public HTTPS with a valid TLS certificate** from cloud sandboxes; an
  internal/self-signed Seafile only works from a local environment
  (Vibe Code CLI/Desktop, VPN). Note: the Work Web code interpreter has
  **no network access** — in Work Web chats use the Studio HTTP connector
  tools instead of these scripts.
- Environment variables (never hardcode, never commit):
  - `SEAFILE_SERVER_URL` — e.g. `https://seafile.example.org`
  - `SEAFILE_API_TOKEN` — **account API token** from the Seafile web UI
    (Avatar → Settings → API Token). These scripts implement the account API
    (`/api2/...`), so they require an account token; repo-scoped library
    tokens use the separate `/api/v2.1/via-repo-token/...` routes and are not
    supported here (a scoped repo-token mode can be added later). In Mistral
    sandboxes bind the token via `secrets=` / `header_bindings` (Secrets
    Manager), locally via env or a secret file.

## Scripts

Canonical entry point: `scripts/seafile_api.py`. All commands print JSON.

```bash
export SEAFILE_SERVER_URL="https://seafile.example.org"
export SEAFILE_API_TOKEN="..."

python3 scripts/seafile_api.py repos                          # list libraries
python3 scripts/seafile_api.py repo <repo_id>                 # library detail
python3 scripts/seafile_api.py ls <repo_id> --path /docs/     # directory listing
python3 scripts/seafile_api.py ls <repo_id> --recursive       # recursive listing
python3 scripts/seafile_api.py file <repo_id> --path /a.md    # file detail
python3 scripts/seafile_api.py download <repo_id> --path /a.md --out a.md
python3 scripts/seafile_api.py search "report" --repo-id <repo_id>   # repo-scoped; account token
python3 scripts/seafile_api.py trash <repo_id>                # trash listing
python3 scripts/seafile_api.py upload-link <repo_id> --path /docs/   # write op
python3 scripts/seafile_api.py upload <repo_id> --path /docs/ --file local.pdf   # write op

# filemap: inventory of a repo path (change detection basis)
python3 scripts/seafile_api.py filemap <repo_id> --path / --out filemap.json
# diff against a previous filemap -> added/removed/changed
python3 scripts/seafile_api.py filemap <repo_id> --diff filemap.old.json
```

`--server` / `--token` flags exist as a fallback to the env vars; prefer the
env vars so tokens never end up in shell history or command lines.

## filemap and change detection

`filemap` walks the repo recursively and writes a `seafile-filemap` JSON:
`files` maps each repo path to `{type, size, mtime, mtime_iso, id}`. Seafile
has no changes webhook in the standard scope, so sync/change detection is
**mtime-polling** on the dir listing: run `filemap`, then `--diff` against
the previous filemap to get `added` / `removed` / `changed`.

For office-intelligence cloud-atlas, `filemap.json` and its curation belong in
the `Office – <Org> – Data` library; the Seafile cloud itself stays the SSOT
(read path; writing to Seafile is secondary).

## Write operations

Uploads go through `upload-link` + multipart POST and are implemented in
`seafile_api.py upload`. Treat all write operations as **manual-approval
only** (in Studio/Work: keep write tools on manual approval; read tools may
be pre-authorized). Multipart upload is typically not converted by an
OpenAPI/HTTP-connector import — that is why the script exists.

## Sandbox notes

- Cloud sandboxes (Vibe Code Web, Studio `MistralSandbox`) only reach
  **public** HTTPS endpoints (`MistralSandbox` needs
  `network=Network.all()`; Work Web code interpreter has no network at all).
- Mind per-command timeouts and egress rate limits; chunk long syncs. The
  sandbox is ephemeral — persist results (filemap.json, downloads) to git or
  a document library, not the sandbox filesystem.
- Large files: cap downloads (`--out` to disk) and chunk processing.

## Platform connector setup (platform-specific — not part of this skill)

To use Seafile as ready-made tools (chats/agents/workflows, e.g. in Mistral
Studio/Work where the code interpreter has no network), register an HTTP
connector for the Seafile server root with API-token auth
(`Authorization: Token <api-token>`) and import the OpenAPI spec from this
repo (`spec/seafile-openapi.yaml`) or the official
https://github.com/haiwen/seafile-open-api spec. Platform-specific setup
steps (UI labels, credentials, visibility, approvals) live in
`adapters/mistral/README.md` in the repo — this skill stays platform-neutral.

## References

- Official OpenAPI spec: https://github.com/haiwen/seafile-open-api
- Seafile Admin Manual, Web API v2.1: https://manual.seafile.com/latest/develop/web_api_v2.1/
- API reference (readme.io): https://seafile-api.readme.io/reference/introduction
- Agent Skills standard: https://agentskills.io
