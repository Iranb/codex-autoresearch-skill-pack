#!/usr/bin/env python3
"""Read .autoreskill memory."""

from __future__ import annotations

import argparse
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    args = parser.parse_args()
    path = Path(args.project).expanduser().resolve() / ".autoreskill" / "memory.md"
    if not path.exists():
        raise SystemExit(f"missing {path}")
    print(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()
