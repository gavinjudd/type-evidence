# Agent integration

The same Python API powers the JSON CLI and MCP adapter. Any agent that can run a process can use the CLI. An agent without local tool access can receive a shortlist and comparison manifest; it cannot independently resolve or verify local assets.

Example MCP configuration (replace the absolute paths with your checkout and venv):

```json
{
  "mcpServers": {
    "type-evidence": {
      "command": "/absolute/path/type-evidence/.venv/bin/type-evidence",
      "args": ["--catalog", "/absolute/path/type-evidence/library/catalog.sqlite", "mcp", "--out", "/absolute/path/type-evidence/library/comparisons"]
    }
  }
}
```

On Windows, `command` is `C:\\path\\type-evidence\\.venv\\Scripts\\type-evidence.exe`. Use absolute paths; clients start subprocesses with different working directories.

The adapter implements newline-delimited stdio JSON-RPC with initialize/initialized, ping, tools/list and tools/call. Supported protocol versions: 2024-11-05, 2025-03-26, 2025-06-18. Tools: `font_search`, `font_inspect`, `font_resolve`, `font_compare`, `font_stats`. Read tools do not write; comparisons create unique directories only under the configured output root. It does not fetch collections, scan arbitrary projects, install fonts, execute metadata or open a network port. A real client may request process/filesystem access according to its own policy.

`font_compare` returns paths and a detailed JSON manifest. Open its local PNG in the agent's image tool. Images are not automatically embedded in MCP responses, to keep context bounded. CLI `project` remains an explicit user/agent action outside the MCP tool surface.

Python use:

```python
from type_evidence.catalog import Catalog
from type_evidence.discovery import search
from type_evidence.render import compare

catalog = Catalog("library/catalog.sqlite")
try:
    result = search(catalog, {"role": "ui", "text": "Retry 1,024", "weight": 400, "italic": False, "limit": 4})
    ids = [item["id"] for item in result["candidates"]]
    compare(catalog, ids, "Retry 1,024", "library/retry-study", sizes=[14, 24])
finally:
    catalog.close()
```

The MCP adapter follows the [stdio transport](https://modelcontextprotocol.io/specification/2025-06-18/basic/transports) and [tool](https://modelcontextprotocol.io/specification/2025-06-18/server/tools) specifications. Protocol tests exercise the handshake and tool calls; they do not establish compatibility with every editor or hosted agent.
