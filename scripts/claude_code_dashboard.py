#!/usr/bin/env python3
"""Serve a read-only localhost dashboard for AlgoVeri Claude Code runs."""

from __future__ import annotations

import argparse
import json
import mimetypes
import os
import sys
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.agent.dashboard_state import DashboardState
from src.agent.experiment_catalog import ExperimentCatalog


ASSET_ROOT = REPO_ROOT / "scripts" / "dashboard"


class DashboardHandler(BaseHTTPRequestHandler):
    state: DashboardState
    catalog: ExperimentCatalog
    default_run: str | None = None
    verbose_requests = False

    def send_bytes(self, content: bytes, content_type: str, status: int = 200) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(content)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self.wfile.write(content)

    def send_json(self, value: object, status: int = 200) -> None:
        self.send_bytes(
            json.dumps(value, separators=(",", ":")).encode(),
            "application/json; charset=utf-8",
            status,
        )

    def do_GET(self) -> None:  # noqa: N802 - BaseHTTPRequestHandler API
        parsed = urlparse(self.path)
        if parsed.path == "/api/health":
            self.send_json({"ok": True, "pid": os.getpid()})
            return
        if parsed.path == "/api/experiments":
            self.send_json({"default_run": self.default_run, "experiments": self.catalog.list()})
            return
        if parsed.path == "/api/comparison":
            query = parse_qs(parsed.query)
            ids = [item for value in query.get("ids", []) for item in value.split(",") if item]
            scope = (query.get("scope") or ["common"])[0]
            self.send_json(self.catalog.compare(ids, scope_mode=scope))
            return
        if parsed.path == "/api/state":
            run_id = (parse_qs(parsed.query).get("run") or [self.default_run or ""])[0]
            experiment = self.catalog.get(run_id) if run_id else None
            value = experiment.dashboard_state() if experiment else self.state.snapshot()
            value["run_id"] = experiment.id if experiment else "live"
            self.send_json(value)
            return
        if parsed.path == "/api/task":
            query = parse_qs(parsed.query)
            name = (query.get("name") or [""])[0]
            run_id = (query.get("run") or [self.default_run or ""])[0]
            experiment = self.catalog.get(run_id) if run_id else None
            detail = experiment.dashboard_detail(name) if experiment else self.state.task_detail(name)
            if detail is None:
                self.send_json({"error": "unknown task"}, HTTPStatus.NOT_FOUND)
            else:
                self.send_json(detail)
            return

        assets = {"/": "index.html", "/app.js": "app.js", "/app.css": "app.css"}
        filename = assets.get(parsed.path)
        if filename is None:
            self.send_json({"error": "not found"}, HTTPStatus.NOT_FOUND)
            return
        path = ASSET_ROOT / filename
        try:
            content = path.read_bytes()
        except OSError:
            self.send_json({"error": f"dashboard asset missing: {filename}"}, HTTPStatus.INTERNAL_SERVER_ERROR)
            return
        content_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        if content_type.startswith("text/") or content_type in {"application/javascript"}:
            content_type += "; charset=utf-8"
        self.send_bytes(content, content_type)

    def log_message(self, format: str, *args: object) -> None:
        if self.verbose_requests:
            super().log_message(format, *args)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--work-root", default=".agent_runs/claude_code_opus5")
    parser.add_argument("--results-root", default="results/claude_code_opus5")
    parser.add_argument("--tasks", help="Comma- or whitespace-separated task names")
    parser.add_argument("--result-model-name", default="claude-code-opus-5")
    parser.add_argument("--runner-pid-file")
    parser.add_argument("--dashboard-pid-file", default="logs/claude_code_dashboard.pid")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--verbose-requests", action="store_true")
    parser.add_argument("--catalog", default="config/dashboard_experiments.json")
    parser.add_argument("--data-root", default="algoveri_data")
    parser.add_argument("--default-run", default="claude-code-hard10")
    return parser.parse_args()


def resolve(path: str) -> Path:
    value = Path(path).expanduser()
    return value.resolve() if value.is_absolute() else (REPO_ROOT / value).resolve()


def main() -> int:
    args = parse_args()
    tasks = list(dict.fromkeys(args.tasks.replace(",", " ").split())) if args.tasks else None
    state = DashboardState(
        work_root=resolve(args.work_root),
        results_root=resolve(args.results_root),
        tasks=tasks,
        result_model_name=args.result_model_name,
        pid_file=resolve(args.runner_pid_file) if args.runner_pid_file else None,
    )
    DashboardHandler.state = state
    try:
        DashboardHandler.catalog = ExperimentCatalog(
            REPO_ROOT,
            resolve(args.catalog),
            resolve(args.data_root),
        )
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 2
    DashboardHandler.default_run = args.default_run
    DashboardHandler.verbose_requests = args.verbose_requests
    pid_path = resolve(args.dashboard_pid_file)
    try:
        server = ThreadingHTTPServer((args.host, args.port), DashboardHandler)
    except OSError as exc:
        print(f"Could not start dashboard on {args.host}:{args.port}: {exc}", file=sys.stderr)
        return 2
    pid_path.parent.mkdir(parents=True, exist_ok=True)
    pid_path.write_text(str(os.getpid()) + "\n")
    print(f"AlgoVeri Claude dashboard: http://{args.host}:{args.port}", flush=True)
    print("The server is read-only and refreshes from JSONL/result files.", flush=True)
    try:
        server.serve_forever(poll_interval=0.5)
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        try:
            if pid_path.read_text().strip() == str(os.getpid()):
                pid_path.unlink()
        except OSError:
            pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
