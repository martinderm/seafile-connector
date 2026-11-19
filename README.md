# seafile-connector

Connector + portable skill for **Seafile** in the Mistral ecosystem, built as
part of the office-intelligence → Mistral Vibe Work/Studio porting (cloud-atlas
needs one connector per cloud storage; Seafile has none in the Mistral catalog
and Seafile Ltd. ships no MCP server).

Design goal: **as platform-independent as possible**. The Seafile REST API,
the OpenAPI spec, and the skill are system-agnostic; everything Mistral-specific
is encapsulated under `adapters/mistral/` so the project can be used and adapted
on multiple platforms (Mistral Studio/Work, Vibe Code, any MCP client via
OpenAPI→MCP proxies).

Research basis: Studio library **„Office Intelligence“** (Seafile-Recherche,
HTTP-Connector-Arbeitsnotiz, Portabilität & Sandbox-Risiken, MCP-Inventar,
Cloud-Atlas-Grobkonzept, Porting-Analyse) and the library **„Knowledge Base“**.

## Architecture

```
┌──────────────────────── platform-independent core ────────────────────────┐
│ spec/seafile-openapi.yaml          curated OpenAPI 3.0 subset of the      │
│                                    official haiwen/seafile-open-api spec   │
│ skills/seafile-connector/          agentskills.io skill (SKILL.md +          │
│   scripts/seafile_api.py           self-contained stdlib client/CLI:       │
│                                    repos, ls, file, download, search,    │
│                                    trash, upload-link, upload, filemap   │
│                                    (+ --diff change detection)            │
└───────────────────────────────────────────────────────────────────────────┘
                              │ used by
┌────────────── Mistral-specific (encapsulated) ──────────────┐
│ adapters/mistral/                                            │
│   README.md               Studio/Work HTTP-connector setup  │
│   connector.example.json  create payload for POST /v1/connectors │
│   register_connector.py   API automation (dry-run default)   │
└──────────────────────────────────────────────────────────────┘
```

**Primary path in Studio/Work: HTTP connector** (protocol `http`, server URL =
Seafile root, API-key auth `Authorization: Token <api-token>`, OpenAPI spec
imported from `spec/`) — no own MCP server, no hosting, one tool per
operation. **Fallback:** community MCP server (e.g. virtUOS/seafile-mcp) for
operations the import skips (multipart upload, share links). **Skill
scripts** cover filemap/change-detection and any environment with network
access (Vibe Code; Studio agent with `MistralSandbox(network=Network.all())`).
In Work Web chats only the connector tools work — the code interpreter there
has no network.

## Layout

| Path | Purpose |
|---|---|
| `spec/seafile-openapi.yaml` | curated OpenAPI spec for the HTTP-connector import (read path + upload link; search needs an account token) |
| `skills/seafile-connector/SKILL.md` | portable skill (agentskills.io) |
| `skills/seafile-connector/scripts/seafile_api.py` | stdlib-only client + CLI (see SKILL.md) |
| `adapters/mistral/` | all Mistral-specific integration (setup guide, API automation) |
| `tests/` | unittest suite (mocked HTTP; no network, no secrets) |
| `.github/workflows/tests.yml` | CI: runs the tests on push/PR |

## Quickstart

Skill scripts (any Python 3.10+ with network):

```bash
export SEAFILE_SERVER_URL="https://seafile.example.org"
export SEAFILE_API_TOKEN="..."   # account token (account API /api2/...)
python3 skills/seafile-connector/scripts/seafile_api.py repos
python3 skills/seafile-connector/scripts/seafile_api.py filemap <repo_id> --out filemap.json
python3 skills/seafile-connector/scripts/seafile_api.py filemap <repo_id> --diff filemap.old.json
```

Studio/Work HTTP connector: step-by-step in
[adapters/mistral/README.md](adapters/mistral/README.md).

## Security rules

- **Never commit credentials.** Tokens come from env vars
  (`SEAFILE_API_TOKEN`, `MISTRAL_API_KEY`) or the Mistral Secrets Manager at
  runtime; in Studio sandboxes via `secrets=` / `header_bindings`.
- The curated spec and skill scripts target the **account API** (`/api2/…`),
  so they need an **account token** (repo-scoped library tokens use the
  separate `/api/v2.1/via-repo-token/…` routes — not covered yet). Use least
  privilege. Store tokens in the Secrets Manager, not in spec/skill/repo.
- Write operations (upload) stay on **manual approval**.
- Only public HTTPS with valid TLS is reachable from Mistral cloud
  sandboxes/gateway; internal Seafile → local Vibe Code path.

## Portability

| Layer | Portable? |
|---|---|
| Seafile REST API + API token + official OpenAPI spec | fully system-independent |
| `spec/` + `skills/` (agentskills.io, stdlib) | portable across agent clients (40+ incl. Mistral); other MCP clients can reuse the same spec via OpenAPI→MCP proxies |
| `adapters/mistral/` (connector registration, Secrets Manager, visibility, named credentials) | Mistral-specific, encapsulated; replicable via `POST /v1/connectors` |

Bound to Seafile's API + token — not to Mistral.

## Development

```bash
python3 -m unittest discover -s tests -v   # tests (CI enforces)
```

Work on `vibe/<slug>-dd7e4e` branches, open a draft PR, request a Copilot
review before merge. See [CONTRIBUTING.md](CONTRIBUTING.md) and
[AGENTS.md](AGENTS.md).

## References

- Official OpenAPI spec: https://github.com/haiwen/seafile-open-api
- Seafile Web API v2.1 manual: https://manual.seafile.com/latest/develop/web_api_v2.1/
- Mistral docs: [HTTP connectors](https://docs.mistral.ai/studio/connectors/http-connectors), [Manage connectors](https://docs.mistral.ai/studio/connectors/management), [Secrets](https://docs.mistral.ai/studio/agents/learn/agent/secrets)
- Agent Skills standard: https://agentskills.io
