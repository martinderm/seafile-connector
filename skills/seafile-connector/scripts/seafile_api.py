#!/usr/bin/env python3
"""Seafile REST API client and CLI — stdlib-only, platform-independent.

Part of the seafile-connector project. This module deliberately has no
third-party dependencies and no Mistral-specific code, so it runs in any
Python 3.10+ environment with network access (Vibe Code local or cloud
sandbox, a Studio agent sandbox with network enabled, CI).

Configuration (never hardcode credentials — use env vars or a secrets
manager):
  SEAFILE_SERVER_URL  e.g. https://seafile.example.org   (required)
  SEAFILE_API_TOKEN   Seafile API token                  (required)

The token is sent as ``Authorization: Token <token>`` (Seafile token scheme;
a token already starting with ``Token ``/``Bearer `` is passed through).
Seafile >= 11 also accepts ``Bearer <token>``.
"""
from __future__ import annotations

import argparse
import io
import json
import os
import posixpath
import sys
import urllib.error
import urllib.parse
import urllib.request
import uuid
from datetime import datetime, timezone

USER_AGENT = "seafile-connector/1.0 (+https://github.com/martinderm/seafile-connector)"
DEFAULT_TIMEOUT = 30


class SeafileError(Exception):
    """Base error for the seafile_api module."""


class SeafileAPIError(SeafileError):
    """HTTP error returned by the Seafile server."""

    def __init__(self, status: int, body: str, url: str):
        self.status = status
        self.body = body
        self.url = url
        super().__init__(f"Seafile API error {status} for {url}: {body[:500]}")


class SeafileClient:
    """Minimal Seafile REST API (v2.1) client using only the stdlib."""

    def __init__(self, base_url: str, token: str, timeout: int = DEFAULT_TIMEOUT):
        if not base_url:
            raise SeafileError("base_url is required (env SEAFILE_SERVER_URL)")
        if not token:
            raise SeafileError("token is required (env SEAFILE_API_TOKEN)")
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        if token.startswith(("Token ", "Bearer ")):
            self.auth_header = token
        else:
            self.auth_header = f"Token {token}"

    def _request(self, method: str, path: str, params: dict | None = None,
                 raw: bool = False, extra_headers: dict | None = None):
        url = self.base_url + path
        if params:
            query = urllib.parse.urlencode({k: v for k, v in params.items() if v is not None})
            if query:
                url += "?" + query
        headers = {
            "Authorization": self.auth_header,
            "Accept": "application/json",
            "User-Agent": USER_AGENT,
        }
        if extra_headers:
            headers.update(extra_headers)
        req = urllib.request.Request(url, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                payload = resp.read()
        except urllib.error.HTTPError as exc:
            raise SeafileAPIError(exc.code, exc.read().decode("utf-8", "replace"), url) from exc
        except urllib.error.URLError as exc:
            raise SeafileError(f"connection failed for {url}: {exc.reason}") from exc
        if raw:
            return payload
        if not payload:
            return None
        return json.loads(payload.decode("utf-8"))

    # ---- read path ----------------------------------------------------

    def list_repos(self, page: int = 1, per_page: int = 100):
        return self._request("GET", "/api/v2.1/repos/",
                             params={"page": page, "per_page": per_page})

    def get_repo(self, repo_id: str):
        return self._request("GET", f"/api/v2.1/repos/{repo_id}/")

    def list_dir(self, repo_id: str, path: str = "/"):
        return self._request("GET", f"/api/v2.1/repos/{repo_id}/dir/", params={"p": path})

    def get_file(self, repo_id: str, path: str):
        return self._request("GET", f"/api/v2.1/repos/{repo_id}/file/", params={"p": path})

    def get_download_link(self, repo_id: str, path: str):
        return self._request("GET", f"/api/v2.1/repos/{repo_id}/download-link/",
                             params={"p": path})

    def get_upload_link(self, repo_id: str, path: str = "/"):
        return self._request("GET", f"/api/v2.1/repos/{repo_id}/upload-link/",
                             params={"p": path})

    def search_files(self, query: str, repo_id: str | None = None,
                     page: int = 1, per_page: int = 100):
        return self._request("GET", "/api/v2.1/search-file/",
                             params={"q": query, "repo_id": repo_id,
                                     "page": page, "per_page": per_page})

    def list_trash(self, repo_id: str, page: int = 1, per_page: int = 100):
        return self._request("GET", f"/api/v2.1/repos/{repo_id}/trash/",
                             params={"page": page, "per_page": per_page})

    def download_file(self, repo_id: str, path: str) -> bytes:
        return self._request("GET", f"/api2/repos/{repo_id}/file/",
                             params={"p": path, "raw": 1}, raw=True)

    # ---- write path (secondary; keep behind manual approval) ----------

    def upload_file(self, repo_id: str, remote_dir: str, filename: str, data: bytes):
        link = self.get_upload_link(repo_id, remote_dir)
        upload_url = link.get("upload_link") if isinstance(link, dict) else link
        if not upload_url:
            raise SeafileError(f"no upload link returned: {link!r}")
        boundary = uuid.uuid4().hex
        body = b"".join([
            f"--{boundary}\r\nContent-Disposition: form-data; name=\"parent\"\r\n\r\n{remote_dir}\r\n".encode(),
            (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; "
             f"filename=\"{filename}\"\r\nContent-Type: application/octet-stream\r\n\r\n").encode()
            + data + b"\r\n",
            f"--{boundary}--\r\n".encode(),
        ])
        req = urllib.request.Request(
            upload_url,
            data=body,
            headers={
                "Authorization": self.auth_header,
                "Content-Type": f"multipart/form-data; boundary={boundary}",
                "User-Agent": USER_AGENT,
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return resp.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as exc:
            raise SeafileAPIError(exc.code, exc.read().decode("utf-8", "replace"), upload_url) from exc

    # ---- recursive listing / filemap -----------------------------------

    def walk(self, repo_id: str, root: str = "/"):
        """Recursively list a directory tree. Yields (path, entry) tuples."""
        if not root.endswith("/"):
            root += "/"
        for entry in self.list_dir(repo_id, root) or []:
            name = entry.get("name", "")
            path = posixpath.join(root, name)
            yield path, entry
            if entry.get("type") == "dir":
                yield from self.walk(repo_id, path + "/")


def build_filemap(client: SeafileClient, repo_id: str, root: str = "/") -> dict:
    """Build a filemap (inventory) of a repo path for sync/change detection."""
    repo = client.get_repo(repo_id) or {}
    files = {}
    for path, entry in client.walk(repo_id, root):
        record = {"type": entry.get("type")}
        if entry.get("type") == "file":
            record["size"] = entry.get("size")
            record["mtime"] = entry.get("mtime")
            record["id"] = entry.get("id")
            if entry.get("mtime"):
                record["mtime_iso"] = datetime.fromtimestamp(
                    entry["mtime"], tz=timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
        files[path] = record
    return {
        "kind": "seafile-filemap",
        "schema_version": 1,
        "storage": "seafile",
        "server": client.base_url,
        "repo_id": repo_id,
        "repo_name": repo.get("name"),
        "scan_path": root,
        "updated_at": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S"),
        "files": files,
    }


def diff_filemaps(old: dict, new: dict) -> dict:
    """Compare two filemaps; change detection via size/mtime/object id."""
    old_files = old.get("files", {})
    new_files = new.get("files", {})
    added = sorted(p for p in new_files if p not in old_files)
    removed = sorted(p for p in old_files if p not in new_files)
    changed = []
    for path in sorted(set(old_files) & set(new_files)):
        o, n = old_files[path], new_files[path]
        if (o.get("type") != n.get("type") or o.get("size") != n.get("size")
                or o.get("mtime") != n.get("mtime") or o.get("id") != n.get("id")):
            changed.append({"path": path, "old": o, "new": n})
    return {"added": added, "removed": removed, "changed": changed}


def _emit(obj, compact: bool = False) -> None:
    print(json.dumps(obj, indent=None if compact else 2, ensure_ascii=False))


def _build_client(args) -> SeafileClient:
    try:
        return SeafileClient(args.server, args.token)
    except SeafileError as exc:
        raise SystemExit(
            f"error: {exc}\n"
            "set SEAFILE_SERVER_URL and SEAFILE_API_TOKEN in the environment "
            "(or pass --server/--token) — never hardcode tokens in scripts or repos\n"
        )


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(
        prog="seafile_api.py",
        description="Seafile REST API client (stdlib-only). Credentials via "
                    "SEAFILE_SERVER_URL / SEAFILE_API_TOKEN env vars.",
    )
    parser.add_argument("--server", default=os.environ.get("SEAFILE_SERVER_URL"),
                        help="Seafile base URL (default: env SEAFILE_SERVER_URL)")
    parser.add_argument("--token", default=os.environ.get("SEAFILE_API_TOKEN"),
                        help="Seafile API token (default: env SEAFILE_API_TOKEN)")
    parser.add_argument("--compact", action="store_true", help="compact JSON output")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("repos", help="list libraries")
    p.add_argument("--page", type=int, default=1)
    p.add_argument("--per-page", type=int, default=100)

    p = sub.add_parser("repo", help="library detail")
    p.add_argument("repo_id")

    p = sub.add_parser("ls", help="list a directory")
    p.add_argument("repo_id")
    p.add_argument("--path", default="/")
    p.add_argument("--recursive", action="store_true")

    p = sub.add_parser("file", help="file detail")
    p.add_argument("repo_id")
    p.add_argument("--path", required=True)

    p = sub.add_parser("download", help="download a file (raw bytes)")
    p.add_argument("repo_id")
    p.add_argument("--path", required=True)
    p.add_argument("--out", help="output file (default: basename in cwd)")

    p = sub.add_parser("search", help="search files (requires an account token)")
    p.add_argument("query")
    p.add_argument("--repo-id", default=None)
    p.add_argument("--page", type=int, default=1)
    p.add_argument("--per-page", type=int, default=100)

    p = sub.add_parser("trash", help="list trash of a library")
    p.add_argument("repo_id")
    p.add_argument("--page", type=int, default=1)
    p.add_argument("--per-page", type=int, default=100)

    p = sub.add_parser("upload-link", help="get an upload link (write operation)")
    p.add_argument("repo_id")
    p.add_argument("--path", default="/")

    p = sub.add_parser("upload", help="upload a local file (write operation)")
    p.add_argument("repo_id")
    p.add_argument("--path", required=True, help="remote directory, e.g. /docs/")
    p.add_argument("--file", required=True, help="local file to upload")

    p = sub.add_parser("filemap", help="build a file inventory (filemap.json); "
                                       "--diff compares against a previous filemap")
    p.add_argument("repo_id")
    p.add_argument("--path", default="/")
    p.add_argument("--out", help="write the filemap JSON here (default: stdout)")
    p.add_argument("--diff", metavar="OLD_JSON",
                   help="previous filemap file; prints added/removed/changed")

    args = parser.parse_args(argv)
    client = _build_client(args)

    if args.command == "repos":
        _emit(client.list_repos(page=args.page, per_page=args.per_page), args.compact)
    elif args.command == "repo":
        _emit(client.get_repo(args.repo_id), args.compact)
    elif args.command == "ls":
        if args.recursive:
            _emit([{"path": path, **entry} for path, entry in client.walk(args.repo_id, args.path)],
                  args.compact)
        else:
            _emit(client.list_dir(args.repo_id, args.path), args.compact)
    elif args.command == "file":
        _emit(client.get_file(args.repo_id, args.path), args.compact)
    elif args.command == "download":
        data = client.download_file(args.repo_id, args.path)
        out = args.out or posixpath.basename(args.path.rstrip("/"))
        with open(out, "wb") as fh:
            fh.write(data)
        _emit({"path": args.path, "out": out, "bytes": len(data)}, args.compact)
    elif args.command == "search":
        _emit(client.search_files(args.query, repo_id=args.repo_id,
                                  page=args.page, per_page=args.per_page), args.compact)
    elif args.command == "trash":
        _emit(client.list_trash(args.repo_id, page=args.page, per_page=args.per_page), args.compact)
    elif args.command == "upload-link":
        _emit(client.get_upload_link(args.repo_id, args.path), args.compact)
    elif args.command == "upload":
        with open(args.file, "rb") as fh:
            data = fh.read()
        result = client.upload_file(args.repo_id, args.path,
                                    posixpath.basename(args.file), data)
        _emit({"repo_id": args.repo_id, "path": args.path, "file": args.file,
               "result": result}, args.compact)
    elif args.command == "filemap":
        filemap = build_filemap(client, args.repo_id, args.path)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as fh:
                json.dump(filemap, fh, indent=2, ensure_ascii=False)
                fh.write("\n")
        if args.diff:
            with open(args.diff, encoding="utf-8") as fh:
                old = json.load(fh)
            _emit(diff_filemaps(old, filemap), args.compact)
        elif not args.out:
            _emit(filemap, args.compact)


if __name__ == "__main__":
    try:
        main()
    except SeafileError as exc:
        sys.exit(f"error: {exc}")
