"""
CPG Extractor — Generates Code Property Graphs via Joern Docker.

Uses the Joern HTTP server (running in Docker) to generate CPGs from
C and Java source files. Returns raw CPG data as structured Python objects.

This is the bridge between source code and the NormPDG normalization
layer (RC1). The CPG captures data-flow, control-flow, and type
information that tree-sitter cannot.

Usage::

    extractor = CPGExtractor()
    raw_cpg = extractor.extract(source_code, language="c", project="bubble_sort")
"""

from __future__ import annotations

import contextlib
import hashlib
import logging
import tempfile
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


# ─────────────────────────────────────────────────────────────────────────────
# Raw CPG Models
# ─────────────────────────────────────────────────────────────────────────────


class CPGMethod(BaseModel):
    """A method/function extracted from the CPG."""

    name: str
    full_name: str = ""
    signature: str = ""
    line_number: int = 0
    parameters: list[str] = Field(default_factory=list)
    return_type: str = ""
    is_external: bool = False


class CPGVariable(BaseModel):
    """A local variable or parameter in the CPG."""

    name: str
    type_full_name: str = ""
    line_number: int = 0
    code: str = ""
    is_parameter: bool = False


class CPGCall(BaseModel):
    """A function/method call in the CPG."""

    name: str
    method_full_name: str = ""
    line_number: int = 0
    argument_count: int = 0
    code: str = ""


class CPGControlStructure(BaseModel):
    """A control-flow structure in the CPG."""

    control_structure_type: str  # IF, WHILE, FOR, DO, SWITCH, TRY
    condition: str = ""
    line_number: int = 0
    code: str = ""


class CPGDataFlowEdge(BaseModel):
    """A data-flow edge (reaching def) in the CPG.

    Represents: variable `name` is defined at `def_line` and reaches
    use at `use_line`.
    """

    variable: str
    def_line: int
    def_code: str = ""
    use_line: int
    use_code: str = ""
    method_name: str = ""


class RawCPG(BaseModel):
    """Raw Code Property Graph extracted from Joern.

    This is the intermediate format between Joern's JSON output and
    the NormPDG. It captures everything the normalizer needs.
    """

    language: Literal["c", "java"]
    source_file: str = ""
    methods: list[CPGMethod] = Field(default_factory=list)
    variables: list[CPGVariable] = Field(default_factory=list)
    calls: list[CPGCall] = Field(default_factory=list)
    control_structures: list[CPGControlStructure] = Field(default_factory=list)
    data_flow_edges: list[CPGDataFlowEdge] = Field(default_factory=list)

    @property
    def method_names(self) -> list[str]:
        """Return non-external method names."""
        return [m.name for m in self.methods if not m.is_external]


# ─────────────────────────────────────────────────────────────────────────────
# CPG Extractor
# ─────────────────────────────────────────────────────────────────────────────


class CPGExtractionError(RuntimeError):
    """Raised when CPG extraction fails."""


class CPGExtractor:
    """Generates Code Property Graphs via the Joern Docker server.

    Requires the Joern server to be running::

        docker compose up -d joern

    Parameters
    ----------
    host:
        Joern server hostname.
    port:
        Joern server port (matches docker-compose.yml).
    workspace_dir:
        Directory inside the container where source files are mounted.
        The project root is mounted at ``/code`` via docker-compose.yml.
    """

    def __init__(
        self,
        host: str = "localhost",
        port: int = 8080,
        workspace_dir: str = "/code",
    ) -> None:
        self._host = host
        self._port = port
        self._workspace_dir = workspace_dir
        self._client: Any = None  # Lazy import to avoid Phase 1 breakage

    def _get_client(self) -> Any:
        """Lazily connect to the Joern server."""
        if self._client is None:
            from neuroast.verification.joern_client import JoernClient

            self._client = JoernClient(host=self._host, port=self._port)
        return self._client

    def extract(
        self,
        source_code: str,
        language: Literal["c", "java"],
        project_name: str | None = None,
    ) -> RawCPG:
        """Generate a CPG for a source code string.

        Steps:
        1. Write source to a temp file inside the mounted workspace.
        2. Import via Joern's ``importCode``.
        3. Query for methods, variables, calls, control structures, data flow.
        4. Build and return a RawCPG.

        Parameters
        ----------
        source_code:
            Raw source code string.
        language:
            Source language (``"c"`` or ``"java"``).
        project_name:
            Joern workspace name. Auto-generated if not provided.

        Returns
        -------
        RawCPG
            The extracted Code Property Graph.
        """
        client = self._get_client()

        # Generate a unique project name if not provided
        if project_name is None:
            code_hash = hashlib.md5(source_code.encode()).hexdigest()[:8]
            project_name = f"neuroast_{language}_{code_hash}"

        # Determine file extension
        ext = ".c" if language == "c" else ".java"
        # For Java we need to write to a file named after the public class
        # or a generic name — Joern handles both
        filename = f"input{ext}"

        # Write source to a temp directory that maps into the container
        # The docker-compose mounts the project root at /code
        joern_tmp_dir = Path(".joern_tmp")
        joern_tmp_dir.mkdir(exist_ok=True)
        tmp_dir = Path(tempfile.mkdtemp(prefix="neuroast_cpg_", dir=joern_tmp_dir))
        source_path = tmp_dir / filename
        source_path.write_text(source_code)

        # Path as seen from inside the container
        # Assuming the current working directory is the project root,
        # which is mounted at /code
        container_path = f"/code/{source_path}"

        try:
            # Import the source file into Joern
            logger.info(
                "Importing %s into Joern as project '%s'",
                filename,
                project_name,
            )
            client.import_code(container_path, project_name)

            # Extract CPG components
            methods = self._query_methods(client)
            variables = self._query_variables(client)
            calls = self._query_calls(client)
            control_structures = self._query_control_structures(client)
            data_flow_edges = self._query_data_flow(client)

            return RawCPG(
                language=language,
                source_file=filename,
                methods=methods,
                variables=variables,
                calls=calls,
                control_structures=control_structures,
                data_flow_edges=data_flow_edges,
            )
        except Exception as exc:
            raise CPGExtractionError(f"CPG extraction failed for {filename}: {exc}") from exc
        finally:
            # Clean up the Joern project (but leave server running)
            with contextlib.suppress(Exception):
                client.close_project(project_name)
            # Clean up temp file
            source_path.unlink(missing_ok=True)
            tmp_dir.rmdir()

    def extract_from_file(
        self,
        file_path: Path,
        language: Literal["c", "java"],
        project_name: str | None = None,
    ) -> RawCPG:
        """Extract CPG from a file on disk.

        Uses the file path directly (must be accessible from the container
        if using Docker, or on the local filesystem if using local Joern).
        """
        source_code = file_path.read_text()
        if project_name is None:
            project_name = file_path.stem
        return self.extract(source_code, language, project_name)

    # ─────────────────────────────────────────────────────────────────────────
    # Joern Query Methods
    # ─────────────────────────────────────────────────────────────────────────

    def _query_methods(self, client: Any) -> list[CPGMethod]:
        """Query all methods/functions from the CPG."""
        try:
            raw = client.query(
                "cpg.method.map(m => "
                "(m.name, m.fullName, m.signature, m.lineNumber.getOrElse(-1), "
                "m.parameter.name.l, m.methodReturn.typeFullName, m.isExternal)).l"
            )
            return self._parse_methods(raw)
        except Exception as exc:
            logger.warning("Method query failed: %s", exc)
            # Fallback: just get names
            try:
                raw = client.query("cpg.method.name.l")
                return [CPGMethod(name=n) for n in client._parse_scala_list(raw)]
            except Exception:
                return []

    def _query_variables(self, client: Any) -> list[CPGVariable]:
        """Query all local variables from the CPG."""
        try:
            raw = client.query(
                "cpg.local.map(l => (l.name, l.typeFullName, l.lineNumber.getOrElse(-1), l.code)).l"
            )
            return self._parse_variables(raw)
        except Exception as exc:
            logger.warning("Variable query failed: %s", exc)
            return []

    def _query_calls(self, client: Any) -> list[CPGCall]:
        """Query all function/method calls from the CPG."""
        try:
            raw = client.query(
                "cpg.call.map(c => "
                "(c.name, c.methodFullName, c.lineNumber.getOrElse(-1), "
                "c.argument.size, c.code)).l"
            )
            return self._parse_calls(raw)
        except Exception as exc:
            logger.warning("Call query failed: %s", exc)
            return []

    def _query_control_structures(self, client: Any) -> list[CPGControlStructure]:
        """Query all control structures from the CPG."""
        try:
            raw = client.query(
                "cpg.controlStructure.map(c => "
                '(c.controlStructureType, c.condition.code.headOption.getOrElse(""), '
                "c.lineNumber.getOrElse(-1), c.code)).l"
            )
            return self._parse_control_structures(raw)
        except Exception as exc:
            logger.warning("Control structure query failed: %s", exc)
            return []

    def _query_data_flow(self, client: Any) -> list[CPGDataFlowEdge]:
        """Query data-flow (reaching definitions) from the CPG.

        This is the critical query for semantic verification — it extracts
        def→use chains that the normalizer uses to build the NormPDG.
        """
        try:
            raw = client.query(
                "cpg.method.internal.flatMap(m => "
                "m.local.flatMap(l => "
                "l.referencingIdentifiers.flatMap(ref => "
                "ref.inNext.collectAll[nodes.CfgNode].map(def_ => "
                "(l.name, def_.lineNumber.getOrElse(-1), def_.code, "
                "ref.lineNumber.getOrElse(-1), ref.code, m.name))))).l"
            )
            return self._parse_data_flow(raw)
        except Exception as exc:
            logger.warning("Data flow query failed (this is expected for simple CPGs): %s", exc)
            return []

    # ─────────────────────────────────────────────────────────────────────────
    # Parsers — convert Joern's Scala repr to typed Python objects
    # ─────────────────────────────────────────────────────────────────────────

    @staticmethod
    def _parse_methods(raw: str) -> list[CPGMethod]:
        """Parse Joern method query output."""
        import re

        methods = []
        # Joern returns tuples — we do a regex parse for robustness
        # It may pretty-print with newlines, so we add \s* everywhere
        pattern = re.compile(r'\(\s*"([^"]*?)"\s*,\s*"([^"]*?)"\s*,\s*"([^"]*?)"\s*,\s*(-?\d+)\s*,\s*List\([^)]*\)\s*,\s*"([^"]*?)"\s*,\s*(true|false)\s*\)', re.DOTALL)
        for match in pattern.finditer(raw):
            name, full_name, signature, line, ret_type, is_ext = match.groups()
            methods.append(
                CPGMethod(
                    name=name,
                    full_name=full_name,
                    signature=signature,
                    line_number=int(line),
                    is_external=(is_ext == "true"),
                )
            )
        return methods

    @staticmethod
    def _parse_variables(raw: str) -> list[CPGVariable]:
        """Parse Joern local variable query output."""
        import re

        variables = []
        pattern = re.compile(r'\(\s*"([^"]*?)"\s*,\s*"([^"]*?)"\s*,\s*(-?\d+)\s*,\s*"(.*?)"\s*\)', re.DOTALL)
        for match in pattern.finditer(raw):
            name, type_name, line, code = match.groups()
            variables.append(
                CPGVariable(
                    name=name,
                    type_full_name=type_name,
                    line_number=int(line),
                    code=code,
                )
            )
        return variables

    @staticmethod
    def _parse_calls(raw: str) -> list[CPGCall]:
        """Parse Joern call query output."""
        import re

        calls = []
        pattern = re.compile(r'\(\s*"([^"]*?)"\s*,\s*"([^"]*?)"\s*,\s*(-?\d+)\s*,\s*(\d+)\s*,\s*(?:"""(.*?)"""|"(.*?)")\s*\)', re.DOTALL)
        for match in pattern.finditer(raw):
            name, method_fn, line, argc, code1, code2 = match.groups()
            code = code1 if code1 is not None else code2
            calls.append(
                CPGCall(
                    name=name,
                    method_full_name=method_fn,
                    line_number=int(line),
                    argument_count=int(argc),
                    code=code,
                )
            )
        return calls

    @staticmethod
    def _parse_control_structures(raw: str) -> list[CPGControlStructure]:
        """Parse Joern control structure query output."""
        import re

        structures = []
        pattern = re.compile(r'\(\s*"([^"]*?)"\s*,\s*"(.*?)"\s*,\s*(-?\d+)\s*,\s*"(.*?)"\s*\)', re.DOTALL)
        for match in pattern.finditer(raw):
            cs_type, condition, line, code = match.groups()
            structures.append(
                CPGControlStructure(
                    control_structure_type=cs_type,
                    condition=condition,
                    line_number=int(line),
                    code=code,
                )
            )
        return structures

    @staticmethod
    def _parse_data_flow(raw: str) -> list[CPGDataFlowEdge]:
        """Parse Joern data-flow query output."""
        import re

        edges = []
        pattern = re.compile(r'\(\s*"([^"]*?)"\s*,\s*(-?\d+)\s*,\s*"(.*?)"\s*,\s*(-?\d+)\s*,\s*"(.*?)"\s*,\s*"([^"]*?)"\s*\)', re.DOTALL)
        for match in pattern.finditer(raw):
            var, def_line, def_code, use_line, use_code, method = match.groups()
            edges.append(
                CPGDataFlowEdge(
                    variable=var,
                    def_line=int(def_line),
                    def_code=def_code,
                    use_line=int(use_line),
                    use_code=use_code,
                    method_name=method,
                )
            )
        return edges
