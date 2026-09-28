"""Render STATUS.md for the Elevated Associates workspace from registry.json.

Usage:
    python elevated-associates/ops/ea_status.py          # write STATUS.md
    python elevated-associates/ops/ea_status.py --check  # exit 1 if registry has problems

registry.json is the single source of truth; agents (Routines, sessions, people)
update it, and this script turns it into the one-page board everyone reads.
"""

import argparse
import json
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REGISTRY = ROOT / "registry.json"
STATUS = ROOT / "STATUS.md"

STREAM_STATUSES = {"active", "live", "backend-live", "blocked", "paper-only", "exploring", "retired"}
STALE_DAYS = 7


def load():
    with REGISTRY.open(encoding="utf-8") as f:
        return json.load(f)


def problems(reg):
    found = []
    blocker_ids = {b["id"] for b in reg.get("blockers", [])}
    stream_ids = {s["id"] for s in reg.get("streams", [])}
    for s in reg.get("streams", []):
        if s.get("status") not in STREAM_STATUSES:
            found.append(f"stream {s['id']}: unknown status {s.get('status')!r}")
        for b in s.get("blocked_on", []):
            if b not in blocker_ids:
                found.append(f"stream {s['id']}: blocked_on {b!r} has no blocker entry")
        doc = s.get("doc")
        if doc and not (ROOT / doc).exists():
            found.append(f"stream {s['id']}: doc {doc} is missing")
    for a in reg.get("agents", []):
        for sid in a.get("streams", []):
            if sid != "all" and sid not in stream_ids:
                found.append(f"agent {a['id']}: unknown stream {sid!r}")
    return found


def attention(reg, today):
    rows = []
    for a in reg.get("agents", []):
        if a.get("last_status") == "failed":
            rows.append(f"**{a['name']}** failed on its last run ({a.get('last_run')})")
        last = a.get("last_run")
        if a.get("kind") == "routine" and last:
            age = (today - date.fromisoformat(last)).days
            if age > STALE_DAYS:
                rows.append(f"**{a['name']}** hasn't run in {age} days")
    return rows


def render(reg, today):
    ent = reg["entity"]
    out = [
        f"# {ent['name']} — Status",
        "",
        f"_Generated {today.isoformat()} from `registry.json` by `ops/ea_status.py`. Edit the registry, not this file._",
        "",
        "## Revenue streams",
        "",
        "| Stream | Status | Potential | Automation | Blocked on |",
        "|---|---|---|---|---|",
    ]
    for s in reg["streams"]:
        name = f"[{s['name']}]({s['doc']})" if s.get("doc") else s["name"]
        blocked = ", ".join(s.get("blocked_on", [])) or "—"
        out.append(f"| {name} | {s['status']} | {s.get('revenue_potential', '')} | {s.get('automation', '')} | {blocked} |")

    out += ["", "## Agents & automations", "", "| Agent | Kind | Schedule | Last status | Last run |", "|---|---|---|---|---|"]
    for a in reg["agents"]:
        out.append(f"| {a['name']} | {a['kind']} | {a.get('schedule', '—')} | {a.get('last_status', '')} | {a.get('last_run') or '—'} |")

    flags = attention(reg, today)
    if flags:
        out += ["", "## Needs attention", ""] + [f"- {f}" for f in flags]

    out += ["", "## Needs Nicole (one-time checkpoints)", ""]
    for b in reg.get("blockers", []):
        out.append(f"- **{b['id']}** — {b['what']}. _Action:_ {b['action']} (cost: {b['cost']})")
    out.append("")
    return "\n".join(out)


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--check", action="store_true", help="validate the registry and exit")
    args = parser.parse_args()

    reg = load()
    found = problems(reg)
    for p in found:
        print(f"registry: {p}", file=sys.stderr)
    if args.check:
        return 1 if found else 0

    STATUS.write_text(render(reg, date.today()), encoding="utf-8")
    print(f"wrote {STATUS.relative_to(ROOT.parent)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
