from dataclasses import dataclass


@dataclass(frozen=True)
class UvicornOptions:
    """
    Configuration options for running a Uvicorn server.

    Attributes:
        host (str): The host address to bind the server to.
        port (int): The port number to listen on.
        log_level (str): The logging level for the server.
        reload (bool): Whether to enable auto-reload on code changes.
        workers (int): The number of worker processes to spawn.
    """

    host: str
    port: int
    log_level: str
    reload: bool = False
    workers: int = 1


def run(app_module: str, options: UvicornOptions) -> None:
    """
    Run the given ASGI app module with Uvicorn.

    Args:
        app_module (str): The ASGI app module to run (e.g., "server:app").
        options (UvicornOptions): The configuration options for the Uvicorn server.
    """

    import uvicorn

    uvicorn.run(
        app_module,
        loop="uvloop",
        http="httptools",
        access_log=False,
        host=options.host,
        port=options.port,
        log_level=options.log_level,
        reload=options.reload,
        log_config=None,
        proxy_headers=True,
        workers=options.workers,
    )
