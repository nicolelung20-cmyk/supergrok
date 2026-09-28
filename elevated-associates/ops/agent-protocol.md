# Agent Coordination Protocol

This is how Claude sessions, scheduled Routines, and other AI tools stay in sync without Nicole relaying messages between them.

## Channels, fastest first

| Channel | Latency | Use for |
|---|---|---|
| **Direct session message** (Claude Code Remote `send_message` to a named session) | Seconds | Handing work to a running sibling session |
| **Routine fire** (`fire_trigger` with run-specific text) | About 1 min | Kicking an existing job early, e.g. "re-run sales pulse, Stripe is back" |
| **Daybook artifact DB** (`dashboard/*` docs) | Next page load | Live numbers Nicole sees on her phone |
| **`registry.json` in this repo** | Next commit | Durable state: stream status, agent last-run, blockers |
| **Weekly status Routine** (Fri) | Weekly | Roll-up summary to Nicole |

True "instant, continuous" contact with every AI tool isn't possible: web chat sessions (Grok, ChatGPT, Gemini) have no inbound API. The SuperGrok Bridge in this repo can reach them from Nicole's own machine through her logged-in sessions. It is a local, manual-launch tool, not a cloud service.

## Every run, every agent

1. **Read** `registry.json` and the Daybook `dashboard/venture` doc.
2. **Do** one scoped job, under the [charter](../CHARTER.md) rules.
3. **Write back:** set your agent row's `last_status` (`succeeded` / `failed` / `skipped`) and `last_run`, plus a one-line note in Daybook `dashboard/venture`.
4. **Escalate** only what Nicole alone can do: add or update an entry in `blockers`, and never message her once per issue.
5. **Never wait** on a human click during an unattended run. Skip the step, log it, and move on.

## Handling failures

| Symptom | Likely cause | Response |
|---|---|---|
| Run fails within ~15s | Usage limit hit, or a connector not granted | Mark `failed`, check limits; don't retry in a loop |
| "Weekly limit" in session summary | Plan quota exhausted | Pause lowest-value high-frequency jobs first (hourly refresh) |
| Connector won't load | Needs re-auth | Add a blocker: "reconnect X in claude.ai → Settings → Connectors" |
| Needs an account or key | Identity-bound | Add a blocker with the exact signup URL and the env var name the code expects |

## Routine hygiene

The account has **7 disabled duplicate Routines** from earlier iterations (see [ledger](../ledger/2026-09-interactions.md#routines)). They don't fire or cost anything, but they clutter the list. Delete them once Nicole confirms.
