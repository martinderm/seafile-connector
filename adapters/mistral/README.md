# Mistral adapter — Seafile HTTP connector in Studio/Work

Everything Mistral-specific lives in this folder. The rest of the repo
(`spec/`, `skills/`) is platform-independent.

Primary path: **HTTP connector directly against the Seafile REST API** — no
own MCP server, no hosting. Fallback: a community MCP server (e.g.
[virtUOS/seafile-mcp](https://github.com/virtUOS/seafile-mcp)) only for
operations the OpenAPI import does not convert (multipart upload, share
links).

## Prerequisites

- Seafile server reachable over **public HTTPS with a valid TLS certificate**
  (the Studio/Work connector gateway and cloud sandboxes cannot reach
  internal/LAN or self-signed servers; those need the local Vibe Code path
  with the skill scripts or a stdio MCP).
- **Admin rights** in Studio/Work to add a custom connector.
- A Seafile **account API token** (web UI: Avatar → Settings → API Token —
  works with an active SSO session and avoids the 2FA header problem of
  `POST /api2/auth-token/`). The curated spec targets the account API
  (`/api2/…`), so it needs an account token; repo-scoped library tokens use
  the separate `/api/v2.1/via-repo-token/…` routes, which are not part of
  this spec (can be added as a second spec/connector later). Use a
  least-privilege account.
- The connector credential (the token as a benutzerdefiniert header) is stored
  **by the Connectors Gateway** — per the Mistral docs, "a connector's token
  never leaves the Connectors Gateway", and you should *not* also declare it as
  an agent `secret`. Never in the spec, skill, scripts, or repo.

## Secrets convention (repo stays example-only)

The repo only contains **generic example values** (`https://seafile.example.org`,
placeholders) — real values never go into git. There are **two runtime stores**,
for two different paths:

1. **Connector credential (Connectors Gateway)** — for the Studio/Work HTTP
   connector. Enter the token once as the benutzerdefiniert custom header
   (`Authorization: Token <…>`) on the connector's credential; the gateway
   stores it and it never reaches the model, session, logs, or repo. Optional:
   mark the credential **shared with the workspace** (`credentials_name`,
   `run_as="deployment"` in agents) so one key serves the whole workspace.
2. **Workspace secrets (Secrets Manager)** — for the **script/skill/agent
   path** (`seafile_api.py`, sandboxes, `register_connector.py`). Referenced
   **by name only**, never by value in code/config (secret names are normalized
   to lowercase):

| Secret name (example) | Value (entered only in Secrets Manager) | Bound as |
|---|---|---|
| `seafile_server_url` | real Seafile root, e.g. `https://…` | `SEAFILE_SERVER_URL` (scripts/agents only — the connector's server URL is part of the connector definition and is set directly on the connector, not via a secret) |
| `seafile_api_token` | Seafile account API token | `SEAFILE_API_TOKEN` (scripts/agents) |

- Agents (Agents SDK) — values must be `MistralSecret` references, not bare
  strings, and both variables the scripts need must be bound:
  `secrets={"SEAFILE_SERVER_URL": agents.MistralSecret.workspace("seafile_server_url", worker_env=True), "SEAFILE_API_TOKEN": agents.MistralSecret.workspace("seafile_api_token", worker_env=True)}`
  or on deploy: `agents deploy --secret-binding SEAFILE_SERVER_URL=secret:workspace:seafile_server_url --secret-binding SEAFILE_API_TOKEN=secret:workspace:seafile_api_token`.
  Sandboxes: `secrets=` / `header_bindings=` — values are injected at runtime.
  With `worker_env=True` the runtime can read them by design — the rule is
  **never commit values to source or logs**, not "never reach code".
- `register_connector.py` reads `SEAFILE_SERVER_URL` / `SEAFILE_API_TOKEN` from the
  environment; locally export them from your secret store, never commit them.

## Setup in Studio/Work (UI)

1. Studio/Work → **Connectors → + Add connector → Add a custom connector**.
2. Protocol **`http`**, server URL = Seafile server root
   (e.g. `https://seafile.example.org`; the API hangs off the root:
   `/api2/…`, `/api/v2.1/…`).
3. Auth = **„benutzerdefiniert“** (custom header; in Studio's HTTP-connector
   dialog the same option is shown as *API key* — key name + value). Set
   header name `Authorization`, value `Token <api-token>` (Seafile token
   scheme; `Bearer <token>` also works on Seafile ≥ 11). The only auth
   choices are **benutzerdefiniert / OAuth / keine** — use benutzerdefiniert,
   not OAuth: Seafile SSO protects the web UI, not the API.
4. Import the OpenAPI spec on the connector page: upload
   `spec/seafile-openapi.yaml` from this repo, or use the public URL of the
   official spec https://github.com/haiwen/seafile-open-api (raw). The URL
   must be public and unauthenticated.
5. Review the import dialog: which operations become tools, which are
   skipped (e.g. multipart upload, some download redirects) and why.
6. Toggle tools individually; set **visibility** (`private` /
   `shared_workspace` / `shared_org`).
7. In Work, per function: **read tools pre-authorized, write tools on
   manual approval**.
8. Test in the **Connectors Debugger**: first read test `list_repos` with a
   read-only token.

### Multiple Seafile accounts

One connector + several **named credentials** (`consumer_scope`
user/workspace/org, `name`, `is_default`; selected at runtime in
agent/workflow via `credentials_name`). Each credential holds one account's
`Authorization: Token …` header.

## API automation

`register_connector.py` creates the connector via `POST /v1/connectors` and
a named credential via `POST /v1/connectors/{id}/{consumer_scope}/credentials`
(the consumer scope is a path segment, e.g. `.../user/credentials`; stdlib
only). It is a **dry-run by default** (`--apply` to execute) and never
prints token values.

```bash
export MISTRAL_API_KEY="..."        # Connector access scope required
export SEAFILE_SERVER_URL="https://seafile.example.org"
export SEAFILE_API_TOKEN="..."      # only needed with --apply

python3 adapters/mistral/register_connector.py                 # dry-run
python3 adapters/mistral/register_connector.py --apply \
    --name seafile --server "$SEAFILE_SERVER_URL" --visibility private
```

After creation, import the OpenAPI spec on the connector page (step 4
above) — or via the API per the current reference — then list tools
(`GET /v1/connectors/{id}/tools`) and verify in the debugger.

See `connector.example.json` for the create payload shape. Endpoints and
fields follow https://docs.mistral.ai/studio/connectors/management and
https://docs.mistral.ai/studio/connectors/http-connectors; verify field
names against the current API reference
(https://docs.mistral.ai/api/endpoint/beta/connectors) before relying on
them.

## Environment matrix

| Seafile reachability | Work Web (chat) | Vibe Code Web / Studio agent (cloud sandbox) | Vibe Code CLI/Desktop (local) |
|---|---|---|---|
| public, HTTPS + valid TLS | HTTP connector tools | connector + skill scripts (`network=all()`) | connector + skill scripts |
| internal/LAN/self-signed | ✗ gateway cannot reach it | ✗ sandbox has no LAN route | ✓ skill scripts / stdio MCP locally |

- Work Web **code interpreter has no network** → in Work Web chats only the
  connector tools work; the skill scripts need Vibe Code or a Studio agent
  with `MistralSandbox(network=Network.all())`.
- Cloud sandboxes: respect per-command timeouts and egress rate limits;
  sandboxes are ephemeral → persist results to git/libraries.

## Sync design (cloud-atlas read path)

- `list_repos` → `list_dir` (mtime/size) → `get_file_detail` /
  `get_download_link` → `search_files` (account token only) → `list_trash`.
- No changes webhook in the standard API → **mtime polling** on dir listings
  (filemap change detection); batches via schedules.
- Writing to Seafile is secondary (cloud stays SSOT): `filemap.json`/curation
  go to the `Office – <Org> – Data` library; use the skill script
  (`seafile_api.py upload`) or an MCP fallback for uploads.
