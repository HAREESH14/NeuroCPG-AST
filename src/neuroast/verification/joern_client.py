"""
Joern CPG Client — Phase 2 Semantic Verification
================================================
Wraps the `cpgqls-client` library to provide a clean, typed Python interface
to the Joern HTTP server running in Docker (docker-compose.yml).

The server is started with:
    docker compose up -d joern

It listens on http://localhost:8080/query-sync (POST).

Usage:
    from neuroast.verification.joern_client import JoernClient

    with JoernClient() as joern:
        joern.import_code("/code/tests/fixtures/sample_bubble_sort.c", "bubble_sort")
        result = joern.query("cpg.method.name.l")
        print(result)  # ["bubbleSort", "main"]
"""

from __future__ import annotations

import contextlib
import logging
from collections.abc import Generator
from contextlib import contextmanager
from typing import Any

logger = logging.getLogger(__name__)

# We import cpgqls_client lazily so Phase-1 (tree-sitter only) works without it.
try:
    from cpgqls_client import CPGQLSClient, import_code_query  # type: ignore[import]

    _CPGQLS_AVAILABLE = True
except ImportError:
    _CPGQLS_AVAILABLE = False


class JoernUnavailableError(RuntimeError):
    """Raised when the Joern server cannot be reached or cpgqls-client is not installed."""


class JoernClient:
    """
    Typed Python client for the Joern CPG HTTP server.

    The Joern server must be running before using this client:
        docker compose up -d joern

    Parameters
    ----------
    host:
        Hostname of the Joern server. Defaults to ``localhost``.
    port:
        Port of the Joern server. Defaults to ``8080`` (matching docker-compose.yml).
    auth_username:
        Optional HTTP basic-auth username (only needed if Joern is started with --server-auth-*).
    auth_password:
        Optional HTTP basic-auth password.
    timeout:
        Socket timeout in seconds for each query (default: 120 s for large CPGs).
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8080,
        auth_username: str | None = None,
        auth_password: str | None = None,
        timeout: int = 120,
    ) -> None:
        if not _CPGQLS_AVAILABLE:
            raise JoernUnavailableError(
                "cpgqls-client is not installed. Install Phase-2 extras: uv pip install -e '.[cpg]'"
            )

        self._host = host
        self._port = port
        self._timeout = timeout

        # Build connection kwargs
        kwargs: dict[str, Any] = {}
        if auth_username and auth_password:
            kwargs["credentials"] = (auth_username, auth_password)

        try:
            self._client = CPGQLSClient(f"{host}:{port}", **kwargs)
            logger.info("JoernClient connected to %s:%d", host, port)
        except Exception as exc:
            raise JoernUnavailableError(
                f"Could not connect to Joern at {host}:{port}. "
                "Is 'docker compose up -d joern' running? "
                f"Original error: {exc}"
            ) from exc

    # ─────────────────────────────────────────────────────────────────────────
    # Core API
    # ─────────────────────────────────────────────────────────────────────────

    def query(self, cpgql: str) -> str:
        """
        Execute a raw CPGQL query string on the Joern server.

        Parameters
        ----------
        cpgql:
            A CPGQL expression string, e.g. ``"cpg.method.name.l"``.

        Returns
        -------
        str
            The ``stdout`` text returned by the Joern server.

        Raises
        ------
        JoernUnavailableError
            If the server returns an error or is unreachable.
        """
        logger.debug("Joern query: %s", cpgql)
        result = self._client.execute(cpgql)
        if result.get("success", "false") not in ("true", True):
            stderr = result.get("stderr", "")
            raise JoernUnavailableError(f"Joern query failed.\nQuery: {cpgql}\nStderr: {stderr}")
        return result.get("stdout", "")

    def import_code(self, path_on_server: str, project_name: str) -> str:
        """
        Import a source file or directory into Joern and generate its CPG.

        Parameters
        ----------
        path_on_server:
            Absolute path **inside the container** (e.g. ``/code/tests/fixtures/foo.c``).
            The project root is mounted at ``/code`` via docker-compose.yml.
        project_name:
            A short identifier for the project (used as Joern workspace name).

        Returns
        -------
        str
            The raw stdout from Joern (e.g. a CPG node count string).
        """
        logger.info("Importing %s into Joern as project '%s'", path_on_server, project_name)
        return self.query(import_code_query(path_on_server, project_name))

    def query_methods(self) -> list[str]:
        """Return a list of all method/function names in the current CPG."""
        raw = self.query("cpg.method.name.l")
        # Joern returns a Scala List repr: List("foo", "bar", ...)
        # We do a simple parse — the full CPG verifier will do proper parsing.
        return self._parse_scala_list(raw)

    def query_control_flow(self) -> str:
        """Return raw control-flow node information for all methods."""
        return self.query("cpg.method.controlStructure.l")

    def query_data_flow(self, source_pattern: str, sink_pattern: str) -> str:
        """
        Run a basic data-flow reachability query.

        Parameters
        ----------
        source_pattern:
            A CPGQL filter expression for sources (e.g. ``"\"scanf\".r"``).
        sink_pattern:
            A CPGQL filter expression for sinks (e.g. ``"\"printf\".r"``).
        """
        query = (
            f"def src = cpg.call.name({source_pattern});"
            f"def snk = cpg.call.name({sink_pattern});"
            f"sink.reachableByFlows(src).p"
        )
        return self.query(query)

    def close_project(self, project_name: str) -> None:
        """Unload a project from Joern's in-memory workspace."""
        self.query(f'close("{project_name}")')
        logger.info("Closed Joern project: %s", project_name)

    # ─────────────────────────────────────────────────────────────────────────
    # Context manager support
    # ─────────────────────────────────────────────────────────────────────────

    def __enter__(self) -> JoernClient:
        return self

    def __exit__(self, *args: object) -> None:
        """Nothing to clean up — the server keeps running in Docker."""
        logger.debug("JoernClient context exited.")

    # ─────────────────────────────────────────────────────────────────────────
    # Helpers
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_scala_list(raw: str) -> list[str]:
        """
        Naively parse a Scala ``List("a", "b", ...)`` string into a Python list.
        This is sufficient for method names; richer structures need JSON export.
        """
        import re

        return re.findall(r'"([^"]*)"', raw)


@contextmanager
def joern_session(
    host: str = "localhost",
    port: int = 8080,
    project_name: str | None = None,
    path_on_server: str | None = None,
) -> Generator[JoernClient, None, None]:
    """
    Context manager that creates a Joern session, optionally imports a file,
    and cleans up the project on exit.

    Example
    -------
    ::

        with joern_session(
            path_on_server="/code/tests/fixtures/sample_bubble_sort.c",
            project_name="bubble_sort",
        ) as joern:
            methods = joern.query_methods()
    """
    client = JoernClient(host=host, port=port)
    try:
        if path_on_server and project_name:
            client.import_code(path_on_server, project_name)
        yield client
    finally:
        if project_name:
            with contextlib.suppress(Exception):
                client.close_project(project_name)
