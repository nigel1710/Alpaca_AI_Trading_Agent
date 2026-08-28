# Alpaca MCP Server Configuration

The Python agent uses `alpaca-py` directly for all trading operations.
For Claude Code to also interact with Alpaca MCP tools interactively (e.g.,
for manual inspection or debugging during development), configure the MCP
server at the **user level** — never inside this repository.

## Setup

Add to `~/.claude/mcp_servers.json` (or your Claude Code user-level MCP config):

```json
{
  "alpaca": {
    "command": "uvx",
    "args": ["alpaca-mcp"],
    "env": {
      "APCA_API_KEY_ID": "YOUR_PAPER_API_KEY",
      "APCA_API_SECRET_KEY": "YOUR_PAPER_SECRET_KEY",
      "APCA_API_BASE_URL": "https://paper-api.alpaca.markets"
    }
  }
}
```

**IMPORTANT:**
- Do **NOT** commit credential values to the repository.
- Set credentials only in your user-level MCP configuration or directly
  in your shell environment (`export APCA_API_KEY_ID=...`).
- Only use the paper trading endpoint (`https://paper-api.alpaca.markets`).
- The file `mcp/alpaca_mcp_local.json` is gitignored — you may create it
  locally with your credentials for convenience, but it will never be committed.

## Verify connection

```bash
# Via MCP (if configured)
# Ask Claude: "What is my Alpaca account equity?"

# Via CLI (direct)
python -m cli.main scan --verbose
```
