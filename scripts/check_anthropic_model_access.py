#!/usr/bin/env python3
"""Check Claude model metadata access without generating tokens."""

import argparse
import os


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("model", nargs="?", default="claude-opus-5")
    args = parser.parse_args()

    api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
    if not api_key:
        print("Set ANTHROPIC_API_KEY before checking model access.")
        return 2

    try:
        from anthropic import Anthropic

        model = Anthropic(api_key=api_key).models.retrieve(model_id=args.model)
    except Exception as exc:
        status = getattr(exc, "status_code", None)
        suffix = f" (HTTP {status})" if status else ""
        print(f"Unable to retrieve {args.model}: {type(exc).__name__}{suffix}")
        return 1

    print(f"Anthropic model access confirmed: {model.id}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
