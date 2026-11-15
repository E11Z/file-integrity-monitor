"""Generate a folder of fake files to try the monitor on. All content is made up."""

from __future__ import annotations

import argparse
import random
import shutil
from pathlib import Path

DEFAULT_DIR = "sample_data"
MARKER = ".fim_sample"

# Plausible-looking but entirely fictional files, like a small web app's config folder.
SAMPLE_FILES = {
    "config/app.ini": "[server]\nhost = 127.0.0.1\nport = 8080\ndebug = false\n",
    "config/users.txt": "alice (fake)\nbob (fake)\ncarol (fake)\n",
    "scripts/backup.sh": "#!/bin/sh\necho 'pretend backup of /tmp/example'\n",
    "docs/README.txt": "This folder contains fake sample data for the file integrity monitor.\n",
    "logs/app.txt": "2026-01-01 00:00:00 INFO started (fake log line)\n",
}


def write_samples(target: Path, seed: int) -> list[Path]:
    # Seeded so every run produces identical bytes, which keeps demos repeatable.
    rng = random.Random(seed)
    written = []
    for rel, text in SAMPLE_FILES.items():
        path = target / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        written.append(path)
    blob = target / "data/random.bin"
    blob.parent.mkdir(parents=True, exist_ok=True)
    blob.write_bytes(bytes(rng.getrandbits(8) for _ in range(4096)))
    written.append(blob)
    return written


def tamper(target: Path) -> None:
    """Simulate an intruder: modify one file, delete one, drop a new one."""
    with (target / "config/app.ini").open("a") as handle:
        handle.write("debug = true\n")
    (target / "logs/app.txt").unlink()
    (target / "scripts/evil.sh").write_text("#!/bin/sh\necho 'fake dropped script'\n")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Create fake sample data for fim.py.")
    parser.add_argument("--dir", type=Path, default=Path(DEFAULT_DIR), help="output folder")
    parser.add_argument("--seed", type=int, default=42, help="random seed")
    parser.add_argument(
        "--tamper", action="store_true",
        help="modify existing sample data to simulate changes",
    )
    args = parser.parse_args(argv)

    if args.tamper:
        tamper(args.dir)
        print(f"Tampered with {args.dir}: 1 changed, 1 deleted, 1 added")
        return 0
    # Start clean so leftovers from an earlier --tamper don't leak into a new baseline,
    # but only wipe folders we created, never an arbitrary path the user typed by mistake.
    if args.dir.exists():
        if not (args.dir / MARKER).is_file():
            parser.error(f"{args.dir} exists and was not created by this script, refusing to delete it")
        shutil.rmtree(args.dir)
    files = write_samples(args.dir, args.seed)
    (args.dir / MARKER).write_text("created by generate_sample_data.py\n")
    print(f"Wrote {len(files)} fake files to {args.dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
