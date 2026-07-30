#!/usr/bin/env python3
from __future__ import annotations

import argparse
import os

from openai import OpenAI


def main() -> None:
    parser = argparse.ArgumentParser(description="Check OpenAI model metadata access without generation")
    parser.add_argument("models", nargs="+", help="OpenAI model IDs to retrieve")
    args = parser.parse_args()

    if not os.environ.get("OPENAI_API_KEY"):
        raise SystemExit("OPENAI_API_KEY is not set")

    client = OpenAI(api_key=os.environ["OPENAI_API_KEY"].strip())
    failed = False
    for model in args.models:
        try:
            metadata = client.models.retrieve(model)
            print(f"{model}: available (API returned {metadata.id})")
        except Exception as exc:
            failed = True
            print(f"{model}: unavailable ({type(exc).__name__}: {exc})")

    if failed:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
