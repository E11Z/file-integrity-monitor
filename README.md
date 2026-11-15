# File Integrity Monitor

A small command-line tool that records SHA-256 hashes of every file in a folder and later reports which files were added, changed or deleted. This is the core idea behind tools like Tripwire and AIDE, which detect tampering such as edited configs, dropped scripts or wiped logs.

## How it works
1. **`init`** walks the folder recursively and computes a SHA-256 hash of every regular file. It saves the hashes to a JSON baseline file, keyed by each file's path relative to the folder.
2. **`check`** walks the folder again, hashes everything and compares the result to the baseline:
   - a path in the new scan but not the baseline is **ADDED**
   - a path in the baseline but not the new scan is **DELETED**
   - a path in both with a different hash is **CHANGED**
3. The exit code tells scripts and cron jobs what happened: `0` means no changes, `1` means changes were found, `2` means an error (missing folder, or a missing or corrupt baseline).

### Design choices
- **SHA-256, not timestamps or sizes.** Timestamps are easy to fake with `touch`, and a size can stay the same after an edit. Changing a file's contents without changing its SHA-256 hash is not practical.
- **Hashing in chunks.** Files are read 64 KB at a time, so a huge file never has to fit in memory.
- **Relative paths with forward slashes.** The baseline does not depend on where the folder lives or which OS made it, so you can move the folder or compare across machines.
- **Symlinks are skipped.** Following a link could make the tool hash files outside the folder you asked it to watch.
- **The baseline excludes itself.** If you store `baseline.json` inside the watched folder, it is left out of the scan. Otherwise saving it would show up as a change.
- **Separate `init` and `check` commands.** Re-baselining is a deliberate act. A single "do whatever" command could quietly accept an attacker's changes as the new normal.
- **Standard library only.** `hashlib`, `json`, `argparse` and `pathlib` cover everything, so there is nothing extra to install or audit.

## Install
    git clone <repo-url>
    cd file-integrity-monitor
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt

pytest is the only dependency, and only the tests need it.

## Usage
    .venv/bin/python fim.py --help
    .venv/bin/python fim.py init  <folder> [-b baseline.json]
    .venv/bin/python fim.py check <folder> [-b baseline.json]

Try it on fake data:

    .venv/bin/python generate_sample_data.py           # creates sample_data/ with fake files
    .venv/bin/python fim.py init sample_data           # writes baseline.json
    .venv/bin/python fim.py check sample_data          # no changes, exit 0
    .venv/bin/python generate_sample_data.py --tamper  # edit one file, delete one, add one
    .venv/bin/python fim.py check sample_data          # reports changes, exit 1

The generator only deletes and recreates a folder that it created itself (it checks for a `.fim_sample` marker file), so pointing `--dir` at a real folder by mistake is safe.

## Example output
    $ .venv/bin/python generate_sample_data.py
    Wrote 6 fake files to sample_data
    $ .venv/bin/python fim.py init sample_data
    Baseline saved to baseline.json (7 files)
    $ .venv/bin/python fim.py check sample_data
    OK: no changes detected
    $ .venv/bin/python generate_sample_data.py --tamper
    Tampered with sample_data: 1 changed, 1 deleted, 1 added
    $ .venv/bin/python fim.py check sample_data
    ADDED    scripts/evil.sh
    CHANGED  config/app.ini
    DELETED  logs/app.txt
    Summary: 1 added, 1 changed, 1 deleted
    $ echo $?
    1

(The baseline has 7 files because the `.fim_sample` marker is counted too.)

## Tests
    .venv/bin/python -m pytest

The tests cover chunked hashing, relative paths, skipping symlinks, excluding the baseline, every kind of change, the exit codes, missing and corrupt baselines, and an end-to-end run on the generated sample data.

## What I learned
- A hash only tells you *that* a file changed, not *who* changed it or *why*. You still need logs for that.
- Exit codes make a tool easy to automate. Cron, CI or a shell `if` can react to them without parsing any output.
- The baseline is the weak point. If an attacker can rewrite `baseline.json`, they can hide their changes, so real tools sign the baseline or keep it on read-only or offline storage.
- Small details matter: path separators, symlinks, and a baseline that would otherwise detect itself.

## Limitations
- The baseline is not signed or protected. Anyone who can write to it can make changes invisible.
- Only file contents are checked. Changes to permissions, owners and timestamps are not detected.
- Symlinks and empty directories are ignored.
- It is a one-shot scan, not a real-time watcher. Run it on a schedule (for example from cron) for continuous monitoring.
- A rename shows up as one deletion plus one addition.

## Disclaimer
For educational use on systems you own or have permission to test.
