import importlib.util
import io
import json
import os
import unittest
from unittest import mock

MODULE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "skills", "seafile-connector", "scripts", "seafile_api.py")
spec = importlib.util.spec_from_file_location("seafile_api", MODULE_PATH)
seafile_api = importlib.util.module_from_spec(spec)
spec.loader.exec_module(seafile_api)


class FakeResponse:
    def __init__(self, payload, status=200):
        self.payload = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
        self.status = status

    def read(self, n=-1):
        if n is None or n < 0:
            data, self.payload = self.payload, b""
            return data
        data, self.payload = self.payload[:n], self.payload[n:]
        return data

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def make_client():
    return seafile_api.SeafileClient("https://seafile.example.org", "secret-token")


class ClientTest(unittest.TestCase):
    def test_auth_header_token_prefix_and_passthrough(self):
        self.assertEqual(make_client().auth_header, "Token secret-token")
        self.assertEqual(
            seafile_api.SeafileClient("https://x", "Bearer abc").auth_header, "Bearer abc")

    def test_missing_credentials_raise(self):
        with self.assertRaises(seafile_api.SeafileError):
            seafile_api.SeafileClient("", "t")
        with self.assertRaises(seafile_api.SeafileError):
            seafile_api.SeafileClient("https://x", "")

    def test_list_repos_url_params_and_headers(self):
        client = make_client()
        with mock.patch.object(seafile_api.urllib.request, "urlopen",
                               return_value=FakeResponse([{"id": "r1"}])) as m:
            result = client.list_repos(page=2, per_page=50)
        req = m.call_args[0][0]
        self.assertEqual(req.full_url,
                         "https://seafile.example.org/api2/repos/?page=2&per_page=50")
        self.assertEqual(req.headers["Authorization"], "Token secret-token")
        self.assertEqual(result, [{"id": "r1"}])

    def test_http_error_raises_api_error_with_status(self):
        client = make_client()
        err = seafile_api.urllib.error.HTTPError(
            "https://x", 401, "Unauthorized", {},
            io.BytesIO(b'{"error_msg": "bad token"}'))
        with mock.patch.object(seafile_api.urllib.request, "urlopen", side_effect=err):
            with self.assertRaises(seafile_api.SeafileAPIError) as ctx:
                client.list_repos()
        self.assertEqual(ctx.exception.status, 401)
        self.assertIn("bad token", ctx.exception.body)

    def test_get_file_uses_detail_endpoint(self):
        client = make_client()
        with mock.patch.object(seafile_api.urllib.request, "urlopen",
                               return_value=FakeResponse({"type": "file", "name": "a.md"})) as m:
            client.get_file("r1", "/a.md")
        req = m.call_args[0][0]
        self.assertEqual(
            req.full_url,
            "https://seafile.example.org/api2/repos/r1/file/detail/?p=%2Fa.md")

    def test_download_file_fetches_link_then_bytes(self):
        client = make_client()
        link = "https://seafile.example.org/d/abc123/files/?p=/a.md"
        responses = [FakeResponse(link), FakeResponse(b"RAW-BYTES")]
        with mock.patch.object(seafile_api.urllib.request, "urlopen",
                               side_effect=responses) as m:
            data = client.download_file("r1", "/a.md")
        self.assertEqual(data, b"RAW-BYTES")
        first, second = m.call_args_list[0][0][0], m.call_args_list[1][0][0]
        self.assertEqual(
            first.full_url,
            "https://seafile.example.org/api2/repos/r1/download-link/?p=%2Fa.md")
        self.assertEqual(second.full_url, link)
        self.assertEqual(second.headers["Authorization"], "Token secret-token")

    def test_upload_uses_parent_dir_field(self):
        client = make_client()
        with mock.patch.object(seafile_api.SeafileClient, "get_upload_link",
                               return_value={"upload_link": "https://seafile.example.org/upload/xyz"}), \
             mock.patch.object(seafile_api.urllib.request, "urlopen",
                               return_value=FakeResponse(b'["ok"]')) as m:
            client.upload_file("r1", "/docs/", "a.md", b"hello")
        req = m.call_args[0][0]
        self.assertEqual(req.full_url, "https://seafile.example.org/upload/xyz")
        self.assertIn(b'name="parent_dir"', req.data)
        self.assertIn(b"/docs/", req.data)
        self.assertIn(b'name="file"; filename="a.md"', req.data)

    def test_download_file_to_streams_to_disk(self):
        import tempfile
        client = make_client()
        link = "https://seafile.example.org/d/abc123/?p=/big.bin"
        with mock.patch.object(seafile_api.SeafileClient, "get_download_link",
                               return_value=link), \
             mock.patch.object(seafile_api.urllib.request, "urlopen",
                               return_value=FakeResponse(b"chunk1chunk2")) as m:
            with tempfile.TemporaryDirectory() as tmp:
                out = os.path.join(tmp, "big.bin")
                written = client.download_file_to("r1", "/big.bin", out)
                with open(out, "rb") as fh:
                    self.assertEqual(fh.read(), b"chunk1chunk2")
        self.assertEqual(written, 12)
        self.assertEqual(m.call_args[0][0].full_url, link)

    def test_search_maps_repo_id_to_search_repo_param(self):
        client = make_client()
        with mock.patch.object(seafile_api.urllib.request, "urlopen",
                               return_value=FakeResponse({"results": []})) as m:
            client.search_files("report", repo_id="r1")
        self.assertEqual(
            m.call_args[0][0].full_url,
            "https://seafile.example.org/api2/search/?q=report&search_repo=r1&page=1&per_page=100")

    def test_upload_connection_error_becomes_seafile_error(self):
        client = make_client()
        with mock.patch.object(seafile_api.SeafileClient, "get_upload_link",
                               return_value={"upload_link": "https://seafile.example.org/upload/xyz"}), \
             mock.patch.object(seafile_api.urllib.request, "urlopen",
                               side_effect=seafile_api.urllib.error.URLError("dns")):
            with self.assertRaises(seafile_api.SeafileError):
                client.upload_file("r1", "/docs/", "a.md", b"x")

    def test_list_shared_repos_url(self):
        client = make_client()
        with mock.patch.object(seafile_api.urllib.request, "urlopen",
                               return_value=FakeResponse([])) as m:
            client.list_shared_repos()
        self.assertEqual(m.call_args[0][0].full_url,
                         "https://seafile.example.org/api2/shared-repos/")

    def test_walk_recursion_builds_paths(self):
        client = make_client()
        listing = {
            "/": [
                {"type": "dir", "name": "docs"},
                {"type": "file", "name": "a.md", "size": 5, "mtime": 100, "id": "f1"},
            ],
            "/docs/": [{"type": "file", "name": "b.md", "size": 7, "mtime": 200, "id": "f2"}],
        }
        with mock.patch.object(seafile_api.SeafileClient, "list_dir",
                               side_effect=lambda repo_id, path="/": listing[path]):
            paths = [p for p, _ in client.walk("r1", "/")]
        self.assertEqual(paths, ["/docs", "/docs/b.md", "/a.md"])

    def test_filemap_and_diff(self):
        client = make_client()
        root_listing = [
            {"type": "file", "name": "a.md", "size": 6, "mtime": 200, "id": "f1b"},
            {"type": "file", "name": "new.md", "size": 1, "mtime": 5, "id": "n1"},
        ]
        with mock.patch.object(seafile_api.SeafileClient, "get_repo",
                               return_value={"name": "Lib"}), \
             mock.patch.object(seafile_api.SeafileClient, "list_dir",
                               side_effect=lambda repo_id, path="/": root_listing):
            filemap = seafile_api.build_filemap(client, "r1", "/")
        self.assertEqual(filemap["kind"], "seafile-filemap")
        self.assertEqual(filemap["repo_name"], "Lib")
        self.assertEqual(filemap["files"]["/a.md"]["size"], 6)
        self.assertEqual(filemap["files"]["/a.md"]["mtime_iso"],
                         "1970-01-01 00:03:20")

        old = {"files": {
            "/a.md": {"type": "file", "size": 5, "mtime": 100, "id": "f1"},
            "/gone.md": {"type": "file", "size": 1, "mtime": 1, "id": "x"},
        }}
        diff = seafile_api.diff_filemaps(old, filemap)
        self.assertEqual(diff["added"], ["/new.md"])
        self.assertEqual(diff["removed"], ["/gone.md"])
        self.assertEqual([c["path"] for c in diff["changed"]], ["/a.md"])

    def test_cli_requires_credentials(self):
        with mock.patch.dict(os.environ, {}, clear=True):
            with self.assertRaises(SystemExit):
                seafile_api.main(["repos"])

    def test_cli_repos_with_mocked_client(self):
        with mock.patch.object(seafile_api, "SeafileClient") as cls, \
             mock.patch.dict(os.environ, {"SEAFILE_SERVER_URL": "https://x",
                                          "SEAFILE_API_TOKEN": "t"}):
            cls.return_value.list_repos.return_value = [{"id": "r1"}]
            with mock.patch("sys.stdout", new=io.StringIO()) as out:
                seafile_api.main(["repos"])
            self.assertIn('"id": "r1"', out.getvalue())


if __name__ == "__main__":
    unittest.main()
