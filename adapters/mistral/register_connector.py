#!/usr/bin/env python3
"""Register the Seafile HTTP connector in Mistral Studio/Work via the API.

Mistral-specific adapter (everything Mistral lives in adapters/mistral/).
Stdlib only. Dry-run by default; pass --apply to execute. Token values are
never printed.

Endpoints/fields follow:
  https://docs.mistral.ai/studio/connectors/management
  https://docs.mistral.ai/studio/connectors/http-connectors
Verify against the current API reference
(https://docs.mistral.ai/api/endpoint/beta/connectors) before relying on
field names.

Env:
  MISTRAL_API_KEY      Studio API key with Connector access scope (needed with --apply)
  SEAFILE_SERVER_URL   Seafile server root, e.g. https://seafile.example.org
  SEAFILE_API_TOKEN    Seafile API token (needed with --apply, for the credential)
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import sys
import urllib.error
import urllib.request

API_BASE = "https://api.mistral.ai/v1"
DEFAULT_DESCRIPTION = (
    "Seafile REST API (curated OpenAPI subset: libraries, dir listings, file "
    "details, download/upload links, search, trash) for the cloud-atlas read path"
)


def build_connector_payload(name: str, server: str, visibility: str,
                            description: str) -> dict:
    return {
        "protocol": "http",
        "name": name,
        "title": "Seafile",
        "description": description,
        "server": server.rstrip("/"),
        "visibility": visibility,
    }


def build_credentials_payload(consumer_scope: str, credential_name: str,
                              seafile_token: str) -> dict:
    header = seafile_token if seafile_token.startswith(("Token ", "Bearer ")) \
        else f"Token {seafile_token}"
    return {
        "consumer_scope": consumer_scope,
        "name": credential_name,
        "credentials": {"headers": {"Authorization": header}},
        "is_default": True,
    }


def redact(payload: dict, secret: str | None) -> dict:
    """Deep-copy a payload with the secret value replaced, for dry-run output."""
    cleaned = copy.deepcopy(payload)
    if secret:

        def _walk(node):
            if isinstance(node, dict):
                return {k: ("***" if isinstance(v, str) and secret in v else _walk(v))
                        for k, v in node.items()}
            if isinstance(node, list):
                return [_walk(v) for v in node]
            return node

        cleaned = _walk(cleaned)
    return cleaned


def api_request(api_key: str, method: str, path: str, payload: dict | None = None):
    url = API_BASE + path
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(
        url,
        data=data,
        headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        },
        method=method,
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        sys.exit(f"error: API {exc.code} for {method} {url}: "
                 f"{exc.read().decode('utf-8', 'replace')[:500]}")
    return json.loads(body) if body else None


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        prog="register_connector.py",
        description="Create the Seafile HTTP connector (+ named credential) in "
                    "Mistral Studio/Work. Dry-run unless --apply is given.",
    )
    parser.add_argument("--name", default="seafile", help="connector name (default: seafile)")
    parser.add_argument("--server", default=os.environ.get("SEAFILE_SERVER_URL"),
                        help="Seafile server root (default: env SEAFILE_SERVER_URL)")
    parser.add_argument("--visibility", default="private",
                        choices=["private", "shared_workspace", "shared_org"])
    parser.add_argument("--description", default=DEFAULT_DESCRIPTION)
    parser.add_argument("--consumer-scope", default="user",
                        choices=["user", "workspace", "organization"],
                        help="scope of the credential (default: user)")
    parser.add_argument("--credential-name", default="seafile-default",
                        help="name of the named credential (default: seafile-default)")
    parser.add_argument("--apply", action="store_true",
                        help="actually call the API (default: dry-run only)")
    args = parser.parse_args(argv)

    if not args.server:
        parser.exit(2, "error: --server or env SEAFILE_SERVER_URL is required\n")

    connector_payload = build_connector_payload(
        args.name, args.server, args.visibility, args.description)
    seafile_token = os.environ.get("SEAFILE_API_TOKEN", "")
    credentials_payload = build_credentials_payload(
        args.consumer_scope, args.credential_name, seafile_token) if seafile_token else None

    print("== Plan (dry-run, secrets redacted) ==" if not args.apply else "== Applying ==")
    print("POST /v1/connectors")
    print(json.dumps(redact(connector_payload, seafile_token), indent=2))
    if credentials_payload:
        print(f"POST /v1/connectors/{{id}}/{args.consumer_scope}/credentials "
              f"(name={args.credential_name!r})")
        print(json.dumps(redact(credentials_payload, seafile_token), indent=2))
    else:
        print("(no SEAFILE_API_TOKEN set — credential creation skipped)")
    print("\nNext steps after creation: import the OpenAPI spec on the connector page")
    print("(upload spec/seafile-openapi.yaml from this repo, or the public haiwen/")
    print("seafile-open-api URL), toggle tools (write tools on manual approval),")
    print("list tools (GET /v1/connectors/{id}/tools), test list_repos in the debugger.")

    if not args.apply:
        print("\n(dry-run — re-run with --apply to execute)")
        return

    api_key = os.environ.get("MISTRAL_API_KEY")
    if not api_key:
        parser.exit(2, "error: env MISTRAL_API_KEY is required with --apply\n")
    if not credentials_payload:
        parser.exit(2, "error: env SEAFILE_API_TOKEN is required with --apply "
                       "(credential creation)\n")

    connector = api_request(api_key, "POST", "/connectors", connector_payload)
    connector_id = connector.get("id") or connector.get("name")
    print(f"created connector: id={connector.get('id')} name={connector.get('name')}")
    cred = api_request(
        api_key, "POST",
        f"/connectors/{connector_id}/{args.consumer_scope}/credentials",
        credentials_payload)
    print(f"created credential: {json.dumps(redact(cred, seafile_token), indent=2)}")


if __name__ == "__main__":
    main()
