# Agent Robin

**Status:** exploring. An agent that runs lawful, defensive dark web OSINT investigations through the Robin MCP server (`nicolelung20-cmyk/robin`). The agent definition (`.claude/agents/robin.md`), `CLAUDE.md` and `.mcp.json` were merged in robin#5.

## Needs before real use

- Docker, Tor and one model API key on the machine that runs it.
- Scope rules from the agent definition: lawful use only, no buying or selling, scraped text treated as untrusted.

## Open questions

- Is this an internal research tool or a service sold to clients (for example breach-exposure checks)?
- If a service: package, price and compliance review.

## Next moves

1. Run one real investigation end to end and review the report.
2. Decide internal tool versus paid service, then update this stream.
