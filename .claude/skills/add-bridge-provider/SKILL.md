---
name: add-bridge-provider
description: Add a new chat target (for example Copilot, Perplexity or DeepSeek) to the SuperGrok web bridge alongside Grok, ChatGPT, Gemini and Claude. Use when asked to support another chat site in start.py / app.py.
---

# Add a bridge provider

Follow `docs/ADD_NEW_BRIDGE_WHITEPAPER.md`; it is the authoritative guide. Gemini and Claude are the reference implementations, so copy their patterns.

## Checklist (anchor-based edits, no line numbers)

1. `start.py`: add `DEFAULT_<TARGET>_URL`, `<TARGET>_TARGET_ALIASES`, `<TARGET>_CLI_FLAG_ALIASES`, and the unions `ALL_CHAT_TARGET_ALIASES` / `CHAT_CLI_FLAG_ALIASES`.
2. `start.py`: extend `normalizeChatTarget`, the URL lookup, the argparse flag, `--target` choices, and the login-bridge config.
3. `app.py`: add the alias, label and URL functions, target validation, and DOM selectors (composer, send button, assistant reply).
4. Parts on Nicole's machine (the Desktop hook and the Codex Black extension, per the whitepaper) aren't in this repo. List them in your summary for her to do.
5. Update `README.md` (provider list and flags).

## Verify

- `python3 -m py_compile start.py app.py login_bridge.py`
- `python3 start.py --help` lists the new flag.
- Run the `run-detectors` skill on the changed files.
- Real chat round-trips need a logged-in desktop session, which the cloud container doesn't have. Say so rather than claiming the bridge works.

## Rules

The bridge uses the user's own logged-in session. Never add code that bypasses login, CAPTCHA, paywalls or rate limits.
