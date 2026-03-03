import argparse

from ..config import build_server_config


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="NotebookLM MCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "http"],
        default="stdio",
        help="Transport protocol (default: stdio)",
    )
    parser.add_argument(
        "--multi-tenant",
        action="store_true",
        default=False,
        help="Enable multi-tenant mode (requires --transport http)",
    )
    parser.add_argument(
        "--host",
        default=None,
        help="HTTP server host (default: from SERVER_HOST env or 0.0.0.0)",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=None,
        help="HTTP server port (default: from SERVER_PORT env or 8000)",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> None:
    args = parse_args(argv)

    server_config = build_server_config()
    if args.host is not None:
        server_config.host = args.host
    if args.port is not None:
        server_config.port = args.port
    if args.multi_tenant:
        server_config.multiTenant = True

    if args.transport == "http":
        from .multi_tenant_server import MultiTenantMCPServer
        MultiTenantMCPServer(server_config).run()
    else:
        from .single_tenant_server import SingleTenantMCPServer
        SingleTenantMCPServer(server_config).run()
