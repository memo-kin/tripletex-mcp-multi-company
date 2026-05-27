"""CLI entrypoint.

Defaults to streamable-http on 0.0.0.0:$PORT (Cloud Run injects PORT).
Pass --stdio (or set MCP_TRANSPORT=stdio) to run as a local stdio subprocess.
"""

from __future__ import annotations

import argparse
import os


def main() -> None:
    parser = argparse.ArgumentParser(prog="tripletex-mcp-multi")
    parser.add_argument(
        "--stdio",
        action="store_true",
        help="Run with stdio transport for local Claude Code subprocess use. "
        "Equivalent to setting MCP_TRANSPORT=stdio.",
    )
    args = parser.parse_args()

    if args.stdio:
        os.environ["MCP_TRANSPORT"] = "stdio"

    transport = os.environ.get("MCP_TRANSPORT", "streamable-http")

    # Import after env is set so server.py sees the resolved transport.
    from .server import mcp

    if transport == "stdio":
        mcp.run(transport="stdio")
    else:
        mcp.run(
            transport="streamable-http",
            host="0.0.0.0",
            port=int(os.environ.get("PORT", "8080")),
        )


if __name__ == "__main__":
    main()
