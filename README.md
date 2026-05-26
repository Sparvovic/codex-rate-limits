# Codex Rate Limits

Small Python utility for reading the latest Codex rate-limit snapshot from local
Codex session logs.

It does not call the OpenAI API and does not estimate hidden quotas. It only
prints the most recent `rate_limits` payload already stored in local Codex
session files.

## Usage

```bash
python3 codex_rate_limits.py
```

Print raw JSON:

```bash
python3 codex_rate_limits.py --json
```

Use a specific Codex home:

```bash
python3 codex_rate_limits.py --codex-home ~/.codex
```

Use a specific timezone for reset times:

```bash
python3 codex_rate_limits.py --timezone America/New_York
```

By default, reset times use the local system timezone.

## What It Shows

The script reads the latest local snapshot and prints:

- source session file
- event timestamp
- plan type when present
- primary and secondary rate-limit windows
- used and remaining percentage
- reset time
- reached limit type when present

The window labels come from `window_minutes`, so they adapt if Codex changes the
window size in future snapshots.

## Requirements

- Python 3.11+
- Local Codex session logs

The script uses only the Python standard library.
