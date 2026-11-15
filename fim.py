"""File integrity monitor: baseline a folder with SHA-256 hashes, then detect changes."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_BASELINE = "baseline.json"
BASELINE_VERSION = 1
# Read in chunks so large files never have to fit in memory at once.
CHUNK_SIZE = 64 * 1024

EXIT_OK = 0
EXIT_CHANGED = 1
EXIT_ERROR = 2


@dataclass
class Report:
    added: list[str] = field(default_factory=list)
    changed: list[str] = field(default_factory=list)
    deleted: list[str] = field(default_factory=list)

    @property
    def has_changes(self) -> bool:
        return bool(self.added or self.changed or self.deleted)


def hash_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def scan_folder(folder: Path, exclude: set[Path] | None = None) -> dict[str, str]:
    """Return {relative posix path: sha256} for every regular file under folder."""
    exclude = {p.resolve() for p in (exclude or set())}
    hashes: dict[str, str] = {}
    for path in sorted(folder.rglob("*")):
        # Symlinks are skipped so a link can't make us hash files outside the folder.
        if path.is_symlink() or not path.is_file():
            continue
        if path.resolve() in exclude:
            continue
        # Posix-style relative keys keep baselines portable between OSes.
        hashes[path.relative_to(folder).as_posix()] = hash_file(path)
    return hashes


def save_baseline(folder: Path, hashes: dict[str, str], baseline_path: Path) -> None:
    data = {
        "version": BASELINE_VERSION,
        "folder": str(folder.resolve()),
        "created": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "files": hashes,
    }
    baseline_path.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n")


def load_baseline(baseline_path: Path) -> dict[str, str]:
    data = json.loads(baseline_path.read_text())
    if not isinstance(data, dict) or not isinstance(data.get("files"), dict):
        raise ValueError(f"{baseline_path} is not a valid baseline file")
    return data["files"]


def compare(old: dict[str, str], new: dict[str, str]) -> Report:
    old_keys, new_keys = set(old), set(new)
    return Report(
        added=sorted(new_keys - old_keys),
        deleted=sorted(old_keys - new_keys),
        changed=sorted(k for k in old_keys & new_keys if old[k] != new[k]),
    )


def format_report(report: Report) -> str:
    if not report.has_changes:
        return "OK: no changes detected"
    lines = []
    for label, paths in (("ADDED", report.added), ("CHANGED", report.changed), ("DELETED", report.deleted)):
        lines.extend(f"{label:<8} {p}" for p in paths)
    lines.append(
        f"Summary: {len(report.added)} added, {len(report.changed)} changed, "
        f"{len(report.deleted)} deleted"
    )
    return "\n".join(lines)


def cmd_init(folder: Path, baseline_path: Path) -> int:
    hashes = scan_folder(folder, exclude={baseline_path})
    save_baseline(folder, hashes, baseline_path)
    print(f"Baseline saved to {baseline_path} ({len(hashes)} files)")
    return EXIT_OK


def cmd_check(folder: Path, baseline_path: Path) -> int:
    if not baseline_path.is_file():
        print(f"error: baseline {baseline_path} not found, run 'init' first", file=sys.stderr)
        return EXIT_ERROR
    try:
        old = load_baseline(baseline_path)
    except (ValueError, json.JSONDecodeError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return EXIT_ERROR
    report = compare(old, scan_folder(folder, exclude={baseline_path}))
    print(format_report(report))
    return EXIT_CHANGED if report.has_changes else EXIT_OK


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Detect added, changed and deleted files using SHA-256 hashes.",
        epilog="Exit codes: 0 = no changes, 1 = changes found, 2 = error.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("init", "create a baseline of file hashes"),
        ("check", "compare the folder against the baseline"),
    ):
        p = sub.add_parser(name, help=help_text)
        p.add_argument("folder", type=Path, help="folder to monitor")
        p.add_argument(
            "-b", "--baseline", type=Path, default=Path(DEFAULT_BASELINE),
            help=f"baseline JSON file (default: {DEFAULT_BASELINE})",
        )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if not args.folder.is_dir():
        print(f"error: {args.folder} is not a directory", file=sys.stderr)
        return EXIT_ERROR
    if args.command == "init":
        return cmd_init(args.folder, args.baseline)
    return cmd_check(args.folder, args.baseline)


if __name__ == "__main__":
    sys.exit(main())
