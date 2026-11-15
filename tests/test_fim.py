import hashlib
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fim  # noqa: E402
import generate_sample_data  # noqa: E402


@pytest.fixture
def folder(tmp_path: Path) -> Path:
    root = tmp_path / "watched"
    (root / "sub").mkdir(parents=True)
    (root / "a.txt").write_text("alpha\n")
    (root / "sub" / "b.txt").write_text("bravo\n")
    return root


@pytest.fixture
def baseline(tmp_path: Path) -> Path:
    return tmp_path / "baseline.json"


def test_hash_file_matches_hashlib(tmp_path: Path) -> None:
    path = tmp_path / "f.bin"
    data = b"x" * (fim.CHUNK_SIZE * 2 + 7)  # spans several chunks
    path.write_bytes(data)
    assert fim.hash_file(path) == hashlib.sha256(data).hexdigest()


def test_scan_uses_relative_posix_paths(folder: Path) -> None:
    assert set(fim.scan_folder(folder)) == {"a.txt", "sub/b.txt"}


def test_scan_skips_symlinks(folder: Path, tmp_path: Path) -> None:
    outside = tmp_path / "outside.txt"
    outside.write_text("secret\n")
    (folder / "link.txt").symlink_to(outside)
    assert "link.txt" not in fim.scan_folder(folder)


def test_scan_excludes_baseline_inside_folder(folder: Path) -> None:
    inside = folder / "baseline.json"
    inside.write_text("{}")
    assert "baseline.json" not in fim.scan_folder(folder, exclude={inside})


def test_compare_detects_each_kind() -> None:
    old = {"same": "1", "edit": "2", "gone": "3"}
    new = {"same": "1", "edit": "X", "new": "4"}
    report = fim.compare(old, new)
    assert report.added == ["new"]
    assert report.changed == ["edit"]
    assert report.deleted == ["gone"]
    assert report.has_changes


def test_compare_no_changes() -> None:
    assert not fim.compare({"a": "1"}, {"a": "1"}).has_changes


def test_init_writes_baseline(folder: Path, baseline: Path) -> None:
    assert fim.main(["init", str(folder), "-b", str(baseline)]) == fim.EXIT_OK
    data = json.loads(baseline.read_text())
    assert data["version"] == fim.BASELINE_VERSION
    assert set(data["files"]) == {"a.txt", "sub/b.txt"}


def test_check_clean_exits_zero(folder: Path, baseline: Path, capsys) -> None:
    fim.main(["init", str(folder), "-b", str(baseline)])
    assert fim.main(["check", str(folder), "-b", str(baseline)]) == fim.EXIT_OK
    assert "no changes" in capsys.readouterr().out


def test_check_reports_changes_and_exits_nonzero(folder: Path, baseline: Path, capsys) -> None:
    fim.main(["init", str(folder), "-b", str(baseline)])
    (folder / "a.txt").write_text("tampered\n")
    (folder / "sub" / "b.txt").unlink()
    (folder / "c.txt").write_text("charlie\n")
    capsys.readouterr()

    assert fim.main(["check", str(folder), "-b", str(baseline)]) == fim.EXIT_CHANGED
    out = capsys.readouterr().out
    assert "ADDED    c.txt" in out
    assert "CHANGED  a.txt" in out
    assert "DELETED  sub/b.txt" in out
    assert "1 added, 1 changed, 1 deleted" in out


def test_check_ignores_baseline_stored_in_watched_folder(folder: Path) -> None:
    inside = folder / "baseline.json"
    fim.main(["init", str(folder), "-b", str(inside)])
    assert fim.main(["check", str(folder), "-b", str(inside)]) == fim.EXIT_OK


def test_check_without_baseline_is_error(folder: Path, baseline: Path) -> None:
    assert fim.main(["check", str(folder), "-b", str(baseline)]) == fim.EXIT_ERROR


def test_check_with_corrupt_baseline_is_error(folder: Path, baseline: Path) -> None:
    baseline.write_text("not json")
    assert fim.main(["check", str(folder), "-b", str(baseline)]) == fim.EXIT_ERROR


def test_missing_folder_is_error(tmp_path: Path, baseline: Path) -> None:
    assert fim.main(["init", str(tmp_path / "nope"), "-b", str(baseline)]) == fim.EXIT_ERROR


def test_sample_data_end_to_end(tmp_path: Path, baseline: Path) -> None:
    sample = tmp_path / "sample"
    generate_sample_data.main(["--dir", str(sample)])
    fim.main(["init", str(sample), "-b", str(baseline)])
    generate_sample_data.main(["--dir", str(sample), "--tamper"])
    assert fim.main(["check", str(sample), "-b", str(baseline)]) == fim.EXIT_CHANGED


def test_sample_data_is_deterministic(tmp_path: Path) -> None:
    one, two = tmp_path / "one", tmp_path / "two"
    generate_sample_data.main(["--dir", str(one)])
    generate_sample_data.main(["--dir", str(two)])
    assert fim.scan_folder(one) == fim.scan_folder(two)


def test_generator_refuses_to_delete_foreign_folder(tmp_path: Path) -> None:
    foreign = tmp_path / "mine"
    foreign.mkdir()
    (foreign / "important.txt").write_text("keep me\n")
    with pytest.raises(SystemExit):
        generate_sample_data.main(["--dir", str(foreign)])
    assert (foreign / "important.txt").exists()
