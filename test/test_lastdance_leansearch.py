from __future__ import annotations

import io
import json
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest.mock import patch

from scripts import lastdance_leansearch


class FakeResponse:
    def __init__(self, payload: bytes) -> None:
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def read(self) -> bytes:
        return self.payload


class LastDanceLeanSearchTests(unittest.TestCase):
    def test_service_mode_uses_official_search_payload_and_cache(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            workspace = Path(temporary)
            payload = [[{"name": "Nat.add_comm", "signature": "a + b = b + a"}]]
            arguments = [
                "lastdance_leansearch.py",
                "--url",
                "http://127.0.0.1:8000",
                "--workspace",
                str(workspace),
                "commutativity of addition",
            ]
            output = io.StringIO()
            with (
                patch("sys.argv", arguments),
                patch(
                    "urllib.request.urlopen",
                    return_value=FakeResponse(json.dumps(payload).encode()),
                ) as urlopen,
                redirect_stdout(output),
            ):
                self.assertEqual(lastdance_leansearch.main(), 0)
            request = urlopen.call_args.args[0]
            self.assertEqual(request.full_url, "http://127.0.0.1:8000/search")
            self.assertEqual(
                json.loads(request.data),
                {
                    "query": ["commutativity of addition"],
                    "num_results": 5,
                    "rerank": True,
                },
            )
            self.assertIn("Nat.add_comm", output.getvalue())

            # A repeated query must be served from the harness cache without a
            # second request to the service.
            with (
                patch("sys.argv", arguments),
                patch("urllib.request.urlopen") as second_urlopen,
                redirect_stdout(io.StringIO()),
            ):
                self.assertEqual(lastdance_leansearch.main(), 0)
            second_urlopen.assert_not_called()
            events = [
                json.loads(line)
                for line in (
                    workspace / ".lastdance" / "leansearch_queries.jsonl"
                ).read_text().splitlines()
            ]
            self.assertEqual([event["cached"] for event in events], [False, True])


if __name__ == "__main__":
    unittest.main()
