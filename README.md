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

## Agent Usage Example

This script can be used as a lightweight budget signal for Codex or another
agent. The script does not enforce any behavior by itself; it gives the agent
current local rate-limit context that your prompt can turn into working rules.

Example startup prompt:

```text
Before starting work, run:

python3 codex_rate_limits.py --json

Use the returned primary and secondary limits as your work budget.

- Treat primary as the short 5-hour-style working window.
- Treat secondary as the longer weekly-style working window.
- If both limits have plenty remaining, work normally and use tools as needed.
- If the weekly limit is low and reset is still far away, work more carefully:
  prefer reading more before running expensive commands, batch tool calls, avoid
  speculative exploration, and summarize tradeoffs before large changes.
- Do not intentionally reduce either remaining budget below 15%.
- If continuing would likely cross that 15% floor, stop and ask before doing
  more work.
```

The exact windows should be read from `window_minutes` rather than assumed. For
example, `300` means 5 hours and `10080` means 1 week.

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

## License

MIT. See [LICENSE](LICENSE).
