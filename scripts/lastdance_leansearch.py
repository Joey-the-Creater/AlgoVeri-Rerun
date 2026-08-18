#!/usr/bin/env python3
"""Guarded, cached adapter for Frenzymath LeanSearch's local CLI."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def atomic_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2) + "\n")
    temporary.replace(path)


def append_event(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a") as handle:
        handle.write(json.dumps(value, sort_keys=True) + "\n")


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root")
    parser.add_argument("--python")
    parser.add_argument("--url")
    parser.add_argument("--workspace", required=True)
    parser.add_argument("--num", type=int, default=5)
    parser.add_argument(
        "--rerank", action=argparse.BooleanOptionalAction, default=True
    )
    parser.add_argument("--retrieve-k", type=int)
    parser.add_argument("--timeout", type=int, default=120)
    parser.add_argument("--max-output-chars", type=int, default=24000)
    parser.add_argument("query")
    args = parser.parse_args()

    query = " ".join(args.query.split())
    if not query or len(query) > 1000:
        print("LeanSearch query must contain 1 to 1000 characters.", file=sys.stderr)
        return 2
    if bool(args.url) == bool(args.root):
        print("Configure exactly one of --url or --root.", file=sys.stderr)
        return 2
    root = Path(args.root).resolve() if args.root else None
    search = root / "search.py" if root else None
    workspace = Path(args.workspace).resolve()
    if search is not None and not search.is_file():
        print(f"LeanSearch search.py not found under {root}", file=sys.stderr)
        return 2

    backend = args.url or str(root)
    key = hashlib.sha256(
        f"v2\0{backend}\0{args.num}\0{args.rerank}\0{args.retrieve_k}\0{query}".encode()
    ).hexdigest()
    cache_path = workspace / ".lastdance" / "leansearch_cache" / f"{key}.json"
    query_log = workspace / ".lastdance" / "leansearch_queries.jsonl"
    started = datetime.now(timezone.utc).isoformat()
    cached = False
    if cache_path.is_file():
        try:
            payload = json.loads(cache_path.read_text())
            cached = True
        except (OSError, json.JSONDecodeError):
            cached = False
    if not cached:
        try:
            if args.url:
                endpoint = args.url.rstrip("/")
                if not endpoint.endswith("/search"):
                    endpoint += "/search"
                body: dict[str, Any] = {
                    "query": [query],
                    "num_results": args.num,
                    "rerank": args.rerank,
                }
                if args.retrieve_k is not None:
                    body["retrieve_k"] = args.retrieve_k
                request = urllib.request.Request(
                    endpoint,
                    data=json.dumps(body).encode(),
                    headers={
                        "Content-Type": "application/json",
                        "User-Agent": "LastDance-AlgoVeri/2",
                    },
                    method="POST",
                )
                with urllib.request.urlopen(request, timeout=args.timeout) as response:
                    raw_output = response.read().decode()
            else:
                if not args.python:
                    print("--python is required with --root.", file=sys.stderr)
                    return 2
                command = [
                    args.python,
                    str(search),
                    "--json",
                    "--num",
                    str(args.num),
                    query,
                ]
                completed = subprocess.run(
                    command,
                    cwd=root,
                    env=os.environ.copy(),
                    capture_output=True,
                    text=True,
                    timeout=args.timeout,
                )
                if completed.returncode != 0:
                    append_event(
                        query_log,
                        {
                            "timestamp": started,
                            "query": query,
                            "cached": False,
                            "status": "error",
                            "returncode": completed.returncode,
                            "stderr": completed.stderr[-2000:],
                        },
                    )
                    print(completed.stderr[-4000:] or "LeanSearch failed.", file=sys.stderr)
                    return 1
                raw_output = completed.stdout
        except (subprocess.TimeoutExpired, TimeoutError):
            append_event(
                query_log,
                {"timestamp": started, "query": query, "cached": False, "status": "timeout"},
            )
            print(f"LeanSearch timed out after {args.timeout} seconds.", file=sys.stderr)
            return 1
        except urllib.error.URLError as exc:
            append_event(
                query_log,
                {
                    "timestamp": started,
                    "query": query,
                    "cached": False,
                    "status": "error",
                    "error": str(exc),
                },
            )
            print(f"LeanSearch service failed: {exc}", file=sys.stderr)
            return 1
        try:
            payload = json.loads(raw_output)
        except json.JSONDecodeError as exc:
            print(f"LeanSearch returned invalid JSON: {exc}", file=sys.stderr)
            return 1
        atomic_json(cache_path, payload)

    rendered = json.dumps(payload, indent=2, ensure_ascii=False)
    if len(rendered) > args.max_output_chars:
        rendered = rendered[: args.max_output_chars] + "\n... [truncated by LastDance]"
    append_event(
        query_log,
        {
            "timestamp": started,
            "query": query,
            "cached": cached,
            "status": "ok",
            "cache_key": key,
            "backend": backend,
            "rerank": args.rerank,
            "retrieve_k": args.retrieve_k,
            "result_characters": len(rendered),
        },
    )
    print(rendered)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
