"""Keep the editable template's BM25 snapshot identical to the builder's source."""

import argparse
import sys
from pathlib import Path


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check", action="store_true", help="Fail without changing files"
    )
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    source = root / "core/src/search.rs"
    target = root / "templates/search-service/native/src/search.rs"
    contents = source.read_bytes()
    if args.check:
        if not target.is_file() or target.read_bytes() != contents:
            print(
                "Search template snapshot is out of date; run this script without --check.",
                file=sys.stderr,
            )
            return 1
        print("Search template snapshot matches core/src/search.rs")
    else:
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(contents)
        print(f"Updated {target.relative_to(root)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
