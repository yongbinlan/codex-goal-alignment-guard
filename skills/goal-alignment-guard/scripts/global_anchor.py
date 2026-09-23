"""Preview/apply an opt-in global instruction block. No network or credentials."""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
from pathlib import Path
import stat
import tempfile
import uuid

START = "<!-- goal-alignment-guard:start -->"
END = "<!-- goal-alignment-guard:end -->"


def is_link(path: Path) -> bool:
    try:
        attributes = getattr(path.lstat(), "st_file_attributes", 0)
    except FileNotFoundError:
        return False
    # st_file_attributes also works on Python versions before Path.is_junction.
    if attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400):
        return True
    return path.is_symlink()


def resolve_home(value: str | None) -> Path:
    if value is None:
        return Path.home() / ".codex"
    if not value.strip():
        raise ValueError("Empty Codex home is unsafe; provide the configuration directory explicitly")
    return Path(value)


def safe_target(home: Path) -> Path:
    raw = home.expanduser().absolute()
    for item in (raw, *raw.parents):
        if is_link(item):
            raise ValueError("Linked configuration paths require manual review")
    home = Path(os.path.abspath(raw))
    if home == Path(home.anchor) or home == Path(os.path.abspath(Path.home())):
        raise ValueError("Choose the Codex configuration directory, not a drive or user-home root")
    if not home.is_dir():
        raise ValueError("Codex home must already exist; no configuration directory is created")
    target = home / "AGENTS.md"
    override = home / "AGENTS.override.md"
    if is_link(target) or is_link(override):
        raise ValueError("Linked instruction files require manual review")
    if override.exists() and override.read_text(encoding="utf-8-sig").strip():
        raise ValueError("AGENTS.override.md is active; resolve precedence manually first")
    if target.exists() and not target.is_file():
        raise ValueError("AGENTS.md is not a regular file")
    return target


def proposed_bytes(old: bytes, snippet: str, remove: bool = False) -> bytes:
    # Preserve every pre-existing byte; updates only touch this marked block.
    old.decode("utf-8-sig")
    start, end = START.encode(), END.encode()
    if old.count(start) != old.count(end) or old.count(start) > 1:
        raise ValueError("Ambiguous or incomplete anchor markers; manual review required")
    newline = "\r\n" if b"\r\n" in old else "\n"
    block = (START + "\n" + snippet.strip() + "\n" + END).replace("\r\n", "\n")
    block = block.replace("\n", newline).encode("utf-8")
    if start in old:
        a, b = old.index(start), old.index(end) + len(end)
        if b <= a:
            raise ValueError("Anchor end precedes start")
        return old[:a] + (b"" if remove else block) + old[b:]
    if remove:
        return old
    separator = (newline * 2).encode() if old else b""
    return old + separator + block + newline.encode()


def configure(home: Path, *, apply: bool = False, remove: bool = False) -> dict:
    target = safe_target(home)
    snippet = (Path(__file__).resolve().parents[1] / "references" / "global-anchor.md").read_text(encoding="utf-8")
    existed = target.exists()
    old = target.read_bytes() if existed else b""
    proposed = proposed_bytes(old, snippet, remove)
    result = {"target": str(target), "operation": "remove" if remove else "configure",
              "status": "unchanged" if proposed == old else "preview", "backup": None}
    if proposed == old:
        return result
    if not apply:
        result["proposed_anchor"] = "(remove managed block only)" if remove else snippet
        return result
    # Best-effort concurrent-edit detection, not a cross-process locking protocol.
    safe_target(home)
    if target.exists() != existed or (existed and target.read_bytes() != old):
        raise ValueError("Instructions changed during setup; inspect and retry")
    if existed:
        stamp = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        backup = target.with_name(f"AGENTS.md.before-goal-alignment-{stamp}-{uuid.uuid4().hex[:8]}.bak")
        backup_fd = os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(backup_fd, "wb") as handle:
            handle.write(old)
        result["backup"] = str(backup)
    fd, temporary = tempfile.mkstemp(prefix=".goal-alignment-", suffix=".tmp", dir=target.parent)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(proposed)
            handle.flush()
            os.fsync(handle.fileno())
        safe_target(home)
        if target.exists() != existed or (existed and target.read_bytes() != old):
            raise ValueError("Instructions changed before write; leaving them untouched")
        os.replace(temporary, target)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    if target.read_bytes() != proposed:
        raise ValueError("Post-write verification failed; inspect backup")
    result["status"] = "applied"
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--codex-home", help="An existing Codex configuration directory")
    parser.add_argument("--apply", action="store_true", help="Explicitly write after reviewing the preview and existing rules")
    parser.add_argument("--remove", action="store_true", help="Remove only the managed block; still preview unless --apply")
    args = parser.parse_args()
    try:
        configured = args.codex_home if args.codex_home is not None else os.environ.get("CODEX_HOME")
        result = configure(resolve_home(configured), apply=args.apply, remove=args.remove)
    except (OSError, ValueError, UnicodeError) as exc:
        print(json.dumps({"status": "blocked", "error": str(exc)}, ensure_ascii=False))
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
