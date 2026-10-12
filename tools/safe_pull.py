#!/usr/bin/env python3
"""One-time safe Git update for legacy Lantern checkouts with tracked YAML.

Usage: python tools/safe_pull.py
The script preserves the exact bytes of lan_drive_config.yaml before a
fast-forward update which replaces the tracked YAML with a .yaml_copy template.
No force, reset --hard, stash, or cleanup of unrelated files is performed.
"""
from __future__ import annotations

import argparse
import hashlib
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


class UpgradeError(RuntimeError):
    pass


def git(repo: Path, *args: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, errors="replace", check=False,
    )
    if check and proc.returncode:
        raise UpgradeError(
            "git " + " ".join(args) + " failed: " +
            (proc.stderr.strip() or proc.stdout.strip())
        )
    return proc


def has_blob(repo: Path, revision: str, path: str) -> bool:
    return git(repo, "cat-file", "-e", revision + ":" + path, check=False).returncode == 0


def save_private_backup(repo: Path, data: bytes, backup_dir: Path) -> Path:
    # Outside the Git worktree: never publish a user's local configuration.
    identifier = hashlib.sha256(str(repo).casefold().encode("utf-8")).hexdigest()[:12]
    folder = backup_dir.expanduser().resolve() / identifier
    folder.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = folder / ("lan_drive_config-" + stamp + "-" + uuid4().hex[:8] + ".yaml")
    with path.open("xb") as output:
        output.write(data)
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    return path


def restore_exact(path: Path, data: bytes) -> None:
    temporary = path.with_name(path.name + ".restore-" + uuid4().hex)
    try:
        temporary.write_bytes(data)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)
    if path.read_bytes() != data:
        raise UpgradeError("Restored YAML differs from the original bytes")


def update(repo: Path, branch: str, backup_dir: Path) -> None:
    repo = repo.resolve()
    top = Path(git(repo, "rev-parse", "--show-toplevel").stdout.strip()).resolve()
    if os.path.normcase(str(top)) != os.path.normcase(str(repo)):
        raise UpgradeError("Please run against the checkout root: " + str(top))
    current = git(repo, "symbolic-ref", "--short", "HEAD").stdout.strip()
    if current != branch:
        raise UpgradeError("Expected branch " + branch + ", found " + current)

    git(repo, "fetch", "origin", branch)
    target = "refs/remotes/origin/" + branch
    if git(repo, "merge-base", "--is-ancestor", "HEAD", target, check=False).returncode:
        raise UpgradeError("Local branch is not a fast-forward of origin/" + branch)

    name = "lan_drive_config.yaml"
    yaml_path = repo / name
    tracked = git(repo, "ls-files", "--error-unmatch", "--", name, check=False).returncode == 0
    migration = tracked and not has_blob(repo, target, name) and has_blob(repo, target, name + "_copy")
    original: bytes | None = None
    backed_up: Path | None = None
    config_was_restored = False

    if migration and yaml_path.is_file():
        if git(repo, "diff", "--cached", "--quiet", "--", name, check=False).returncode:
            raise UpgradeError("YAML has staged changes; unstage it before migrating (no changes made)")
        original = yaml_path.read_bytes()
        backed_up = save_private_backup(repo, original, backup_dir)
        print("Config backup:", backed_up, flush=True)
        if git(repo, "diff", "--quiet", "--", name, check=False).returncode:
            # The original bytes are safely backed up. Revert *only this
            # tracked path* so Git can remove it during the rename update.
            git(repo, "restore", "--worktree", "--", name)

    try:
        merge = git(repo, "merge", "--ff-only", target)
        if merge.stdout.strip():
            print(merge.stdout.strip(), flush=True)
    finally:
        if original is not None:
            # On both success and failure, keep the user's local configuration.
            # Once renamed upstream the restored path is Git-ignored.
            restore_exact(yaml_path, original)
            config_was_restored = True
    if migration and config_was_restored:
        if git(repo, "ls-files", "--error-unmatch", "--", name, check=False).returncode == 0:
            raise UpgradeError("The YAML unexpectedly remains tracked; the private backup is at " + str(backed_up))
        print("Preserved machine config (now ignored by Git):", yaml_path)
    print("HEAD:", git(repo, "rev-parse", "--short", "HEAD").stdout.strip())


def main() -> int:
    parser = argparse.ArgumentParser(description="Fast-forward Lantern without losing legacy YAML")
    parser.add_argument("--repo", type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument("--branch", default="main")
    parser.add_argument("--backup-dir", type=Path, default=Path.home() / ".lantern" / "config-backups")
    args = parser.parse_args()
    try:
        update(args.repo, args.branch, args.backup_dir)
    except (UpgradeError, OSError) as exc:
        print("Update stopped:", exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
