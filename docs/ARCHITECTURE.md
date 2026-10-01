# Architecture

## Goal

Embed logged-in chat websites (Grok, ChatGPT, Gemini, Claude, and the other targets listed in `ALL_CHAT_TARGET_ALIASES` in `start.py`) in a Qt WebEngine pane and drive them from a left-side chat shell, or from the command line, by injecting DOM JavaScript. It uses the user's own logged-in session, not a paid API, and never bypasses login, CAPTCHA, paywalls or rate limits.

## Main objects

- `start.py`: launcher and CLI. Parses the chat flags, picks the target, starts or reuses the bridge service, sends CLI requests to it, runs the vendored detectors without Qt, and calls the Flatline placeholder hook.
- `app.py`: the Qt application.
  - `SuperGrokBridgeWindow`: main split-pane window.
  - `BridgeCommandServer`: localhost JSON-line TCP server (default `127.0.0.1:8767`, override with `SUPERGROK_BRIDGE_PORT`) that answers resident CLI calls such as `{"action": "chat", "target": "...", "message": "..."}`. One running service answers one target.
  - `ChatPane`: left-side local chat transcript web engine plus prompt/send row.
  - `ManagedWebView`: common QWebEngineView wrapper with right-click Copy, View Source, and DevTools actions.
  - `GrokPageController` and `buildGrokDomSendScript`: DOM automation. The script finds the composer, fills it, clicks send, then polls the page for the assistant reply. Per-target selectors live in this script.
  - `ToolCallManager`: parses and gates ToolCall fences (see below).
  - `SourceDialog`: Prism-highlighted source viewer with Copy, Copy All, and Save As.
- `login_bridge.py`: per-target login window configuration and the auth-page probe used by `--<target>` with no message.
- `exception_log.py`: JSONL exception sink used across the app.
- `vendor/claude/`: report-only static-analysis detectors (see `vendor/claude/README.md`).
- `gh_pipeline.py`: PAT-based GitHub publishing helper; it drives a chat target through the bridge CLI.
- `flatline/`: placeholder for the Flatline debugger package.

## Layout

```text
+-----------------------------------+-------------------------------------------+
| Left: local QWebEngine chat pane  | Right: live QWebEngine pane for the       |
|                                   | selected target (real logged-in website)  |
| [messages rendered as HTML]       |                                           |
| prompt textbox        [Send]      |                                           |
+-----------------------------------+-------------------------------------------+
```

Each target has its own persistent profile under `data/<target>_profile/`, so logging in to one provider does not log in to another.

## Request flow

1. `python start.py --<target> "message"` normalizes the target (`normalizeChatTarget`) and checks for a running bridge service.
2. With no message, it opens the visible login bridge for that target instead (`configure<Target>LoginBridgeArgs`).
3. The service validates the target, injects the DOM script into the live page, and returns the captured reply as JSON on the same TCP connection.
4. If the selectors fail after the retry budget, the window is revealed for a human to repair.

To add a target, follow `ADD_NEW_BRIDGE_WHITEPAPER.md`.

## Automation strategy

Use Qt WebEngine first, not Selenium/Playwright, because the browser is embedded. Selenium/Playwright are better when they own an external browser instance.

The DOM bridge prefers stable attributes and falls back to generic selectors instead of hard-coded CSS classes. The generic fallbacks are:

- `textarea`
- `[contenteditable="true"]`
- `[role="textbox"]`
- `button[aria-label*="send" i]`
- keyboard Enter fallback

## DevTools

Qt WebEngine is Chromium-based. `start.py` sets `QTWEBENGINE_REMOTE_DEBUGGING` when `--remote-debug-port` is used, and the app also exposes embedded DevTools docks per inspected page when supported by the installed PySide6 build.

Right-click either the chat pane or the live provider pane and choose `Dev Inspect with Chromium DevTools` to open the inspector. The toolbar also has a `Remote DevTools URL` action for `http://127.0.0.1:<port>`.

## jQuery boundary

jQuery is loaded only into the left local chat page. The live provider pages are intentionally kept dependency-free so the app does not inject jQuery or other third-party libraries into a provider's production page.

## ToolCall fence rule

ToolCall parsing intentionally ignores single-backtick inline text. Grok must emit explicit triple-backtick command blocks for commands to be considered:

```toolcall
 dir
```

Accepted fence labels are blank, `toolcall`, `tool`, `bash`, `sh`, `shell`, `cmd`, `bat`, `powershell`, `ps1`, and `zsh`. Other code fences such as `python` are ignored.

## Debugger surfaces

The codebot pass added a minimal FlatLine child-surface contract without importing Qt for probe mode. `python start.py --debugger-query-surfaces` prints `heartbeat poll vardump accepts-proxy` and exits. Runtime heartbeat rows are written to `data/supergrok_bridge_debugger.sqlite3` by `SuperGrokBridgeWindow.emitDebuggerHeartbeatSurface()` on a one-second timer. The heartbeat row stores a compact vardump plus the recent process-table snapshot so the launcher can tell whether Qt is alive and whether the ToolCall watchdog is still polling.

The app does not yet advertise `debugger-exec-command` or `debugger-cron-command`; those should only be exposed after a real DB command processor is added.
