#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
"""Read the latest Codex rate-limit snapshot from local session logs."""

from __future__ import annotations

import argparse
import json
import os
from dataclasses import dataclass
from datetime import datetime, timezone, tzinfo
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


@dataclass(frozen=True)
class RateLimitSnapshot:
    source: Path
    event_timestamp: datetime | None
    rate_limits: dict[str, Any]


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def candidate_codex_homes(explicit: str | None) -> list[Path]:
    raw_candidates: list[Path] = []

    if explicit:
        raw_candidates.append(Path(explicit).expanduser())

    env_home = os.environ.get("CODEX_HOME")
    if env_home:
        raw_candidates.append(Path(env_home).expanduser())

    raw_candidates.append(Path.home() / ".codex")

    # Codex Desktop on WSL often stores user state on the mounted Windows home.
    for home in Path("/mnt/c/Users").glob("*/.codex"):
        raw_candidates.append(home)

    seen: set[Path] = set()
    candidates: list[Path] = []
    for path in raw_candidates:
        resolved = path.resolve()
        if resolved not in seen and resolved.exists():
            seen.add(resolved)
            candidates.append(resolved)
    return candidates


def iter_session_files(codex_home: Path) -> list[Path]:
    session_roots = [
        codex_home / "sessions",
        codex_home / "archived_sessions",
    ]
    files: list[Path] = []

    for session_root in session_roots:
        if session_root.exists():
            files.extend(session_root.rglob("*.jsonl"))

    return sorted(files, key=lambda path: path.stat().st_mtime, reverse=True)


def iter_lines_reverse(path: Path, chunk_size: int = 65_536):
    with path.open("rb") as handle:
        handle.seek(0, os.SEEK_END)
        position = handle.tell()
        buffer = b""

        while position > 0:
            read_size = min(chunk_size, position)
            position -= read_size
            handle.seek(position)
            buffer = handle.read(read_size) + buffer
            lines = buffer.split(b"\n")
            buffer = lines[0]

            for line in reversed(lines[1:]):
                if line:
                    yield line.decode("utf-8", errors="replace")

        if buffer:
            yield buffer.decode("utf-8", errors="replace")


def parse_snapshot_line(line: str, source: Path) -> RateLimitSnapshot | None:
    try:
        item = json.loads(line)
    except json.JSONDecodeError:
        return None

    payload = item.get("payload")
    if not isinstance(payload, dict):
        return None

    rate_limits = payload.get("rate_limits")
    if not isinstance(rate_limits, dict):
        return None

    return RateLimitSnapshot(
        source=source,
        event_timestamp=parse_timestamp(item.get("timestamp")),
        rate_limits=rate_limits,
    )


def find_latest_rate_limits(codex_home: Path, max_files: int) -> RateLimitSnapshot | None:
    session_files = iter_session_files(codex_home)
    if max_files > 0:
        session_files = session_files[:max_files]

    for session_file in session_files:
        try:
            for line in iter_lines_reverse(session_file):
                snapshot = parse_snapshot_line(line, session_file)
                if snapshot:
                    return snapshot
        except OSError:
            continue

    return None


def remaining_percent(limit: dict[str, Any]) -> float | None:
    used = limit.get("used_percent")
    if isinstance(used, int | float):
        return max(0.0, 100.0 - float(used))
    return None


def format_window_minutes(value: Any) -> str | None:
    if not isinstance(value, int | float):
        return None

    minutes = int(value)
    if minutes <= 0:
        return f"{minutes}m"

    if minutes % 10_080 == 0:
        weeks = minutes // 10_080
        return f"{weeks}w" if weeks != 1 else "1w"
    if minutes % 1_440 == 0:
        days = minutes // 1_440
        return f"{days}d" if days != 1 else "1d"
    if minutes % 60 == 0:
        hours = minutes // 60
        return f"{hours}h" if hours != 1 else "1h"
    return f"{minutes}m"


def format_reset(resets_at: Any, tz: tzinfo) -> str:
    if not isinstance(resets_at, int | float):
        return "unknown"

    reset_at = datetime.fromtimestamp(float(resets_at), tz=timezone.utc).astimezone(tz)
    now = datetime.now(timezone.utc).astimezone(tz)
    delta = reset_at - now
    seconds = max(0, int(delta.total_seconds()))
    days, rem = divmod(seconds, 86_400)
    hours, rem = divmod(rem, 3_600)
    minutes = rem // 60

    if days:
        relative = f"{days}d {hours}h {minutes}m"
    elif hours:
        relative = f"{hours}h {minutes}m"
    else:
        relative = f"{minutes}m"

    return f"{reset_at:%Y-%m-%d %H:%M:%S %Z} ({relative})"


def local_timezone() -> tzinfo:
    return datetime.now().astimezone().tzinfo or timezone.utc


def load_timezone(name: str | None) -> tzinfo:
    if not name:
        return local_timezone()

    try:
        return ZoneInfo(name)
    except ZoneInfoNotFoundError as exc:
        raise SystemExit(f"Unknown timezone: {name}") from exc


def render_text(snapshot: RateLimitSnapshot, tz: tzinfo) -> str:
    rate_limits = snapshot.rate_limits

    lines = [
        f"Source: {snapshot.source}",
        f"Event: {snapshot.event_timestamp.isoformat() if snapshot.event_timestamp else 'unknown'}",
        f"Plan: {rate_limits.get('plan_type') or 'unknown'}",
    ]

    for name in ("primary", "secondary"):
        limit = rate_limits.get(name, {})
        if not isinstance(limit, dict):
            lines.append(f"{name}: no data")
            continue

        used = limit.get("used_percent")
        remaining = remaining_percent(limit)
        window = format_window_minutes(limit.get("window_minutes"))
        reset = format_reset(limit.get("resets_at"), tz)

        label = f"{name} ({window})" if window else name
        used_text = f"{float(used):.1f}%" if isinstance(used, int | float) else "unknown"
        remaining_text = f"{remaining:.1f}%" if remaining is not None else "unknown"
        lines.append(f"{label}: {used_text} used, {remaining_text} remaining, resets {reset}")

    reached = rate_limits.get("rate_limit_reached_type")
    if reached:
        lines.append(f"Reached: {reached}")

    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Show the latest local Codex rate-limit snapshot."
    )
    parser.add_argument("--codex-home", help="Codex home directory. Defaults to CODEX_HOME and common local paths.")
    parser.add_argument("--max-files", type=int, default=100, help="Newest session files to scan per Codex home. Use 0 for all.")
    parser.add_argument("--timezone", help="IANA timezone for reset times. Defaults to the local system timezone.")
    parser.add_argument("--json", action="store_true", help="Print the raw snapshot as JSON.")
    args = parser.parse_args()

    snapshots: list[RateLimitSnapshot] = []
    for codex_home in candidate_codex_homes(args.codex_home):
        snapshot = find_latest_rate_limits(codex_home, args.max_files)
        if snapshot:
            snapshots.append(snapshot)

    if not snapshots:
        print("No Codex rate-limit snapshots found in local session logs.")
        return 1

    latest = max(
        snapshots,
        key=lambda item: (
            item.event_timestamp.timestamp() if item.event_timestamp else 0.0,
            item.source.stat().st_mtime,
        ),
    )

    if args.json:
        print(
            json.dumps(
                {
                    "source": str(latest.source),
                    "event_timestamp": latest.event_timestamp.isoformat()
                    if latest.event_timestamp
                    else None,
                    "rate_limits": latest.rate_limits,
                },
                indent=2,
                sort_keys=True,
            )
        )
        return 0

    print(render_text(latest, load_timezone(args.timezone)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
