"""
Unified structural extractor using tree-sitter.

Parses C or Java source code and produces a language-agnostic
ControlFlowGraph — the foundation of Pillar N4 (cross-language matching).

Usage::

    extractor = StructuralExtractor("c")
    cfg = extractor.extract(c_source_code)
    print(cfg.summary())  # {"function": 2, "for_loop": 3, ...}
"""

from __future__ import annotations

import logging
from typing import Literal

from tree_sitter import Language, Node, Parser

from neuroast.symbolic import c_queries, java_queries
from neuroast.verification.structures import ControlFlowGraph, ControlFlowNode

logger = logging.getLogger(__name__)


def _load_language(lang: Literal["c", "java"]) -> Language:
    """Load the tree-sitter grammar for the given language."""
    if lang == "c":
        import tree_sitter_c as tsc  # type: ignore[import-untyped]

        return Language(tsc.language())
    elif lang == "java":
        import tree_sitter_java as tsjava  # type: ignore[import-untyped]

        return Language(tsjava.language())
    else:
        raise ValueError(f"Unsupported language: {lang!r}")


def _get_queries(lang: Literal["c", "java"]) -> tuple[dict[str, str], set[str]]:
    """
    Return (NODE_TYPE_MAP, STRUCTURAL_NODE_TYPES) for the given language.
    """
    if lang == "c":
        return c_queries.NODE_TYPE_MAP, c_queries.STRUCTURAL_NODE_TYPES
    else:
        return java_queries.NODE_TYPE_MAP, java_queries.STRUCTURAL_NODE_TYPES


class StructuralExtractor:
    """
    Extracts a ControlFlowGraph from C or Java source code using tree-sitter.

    The extractor walks the tree-sitter parse tree and builds a nested
    structure of ControlFlowNodes, preserving nesting depth and order.

    Parameters
    ----------
    language:
        Either ``"c"`` or ``"java"``.
    """

    def __init__(self, language: Literal["c", "java"]) -> None:
        self.language: Literal["c", "java"] = language
        self._ts_language = _load_language(language)
        self._parser = Parser(self._ts_language)
        self._node_type_map, self._structural_types = _get_queries(language)

        # Determine which node types represent functions/methods.
        if language == "c":
            self._function_types = {"function_definition"}
        else:
            self._function_types = {"method_declaration", "constructor_declaration"}

        logger.debug("StructuralExtractor initialized for %s", language)

    def extract(self, source_code: str) -> ControlFlowGraph:
        """
        Parse source code and build a ControlFlowGraph.

        Parameters
        ----------
        source_code:
            Raw source code string (C or Java).

        Returns
        -------
        ControlFlowGraph
            The language-agnostic structural fingerprint.
        """
        tree = self._parser.parse(source_code.encode("utf-8"))
        root = tree.root_node

        if root.has_error:
            logger.warning(
                "Parse tree contains errors — extraction may be incomplete. "
                "This is expected for malformed LLM output."
            )

        functions: list[ControlFlowNode] = []
        global_calls: list[ControlFlowNode] = []

        # Walk top-level children to find functions.
        for child in root.children:
            if child.type in self._function_types:
                func_node = self._extract_function(child)
                if func_node:
                    functions.append(func_node)
            elif child.type == "class_declaration" and self.language == "java":
                # Java: dig into the class body to find methods.
                class_body = self._find_child_by_type(child, "class_body")
                if class_body:
                    for member in class_body.children:
                        if member.type in self._function_types:
                            func_node = self._extract_function(member)
                            if func_node:
                                functions.append(func_node)

        logger.debug(
            "Extracted %d functions from %s source (%d lines)",
            len(functions),
            self.language,
            source_code.count("\n") + 1,
        )

        return ControlFlowGraph(
            language=self.language,
            functions=functions,
            global_calls=global_calls,
        )

    # ─────────────────────────────────────────────────────────────────────────
    # Internal extraction methods
    # ─────────────────────────────────────────────────────────────────────────

    def _extract_function(self, node: Node) -> ControlFlowNode | None:
        """Extract a function/method node and its children."""
        name = self._get_function_name(node)
        line = node.start_point[0] + 1  # 1-indexed

        # Find the function body
        body = self._find_function_body(node)
        children: list[ControlFlowNode] = []
        if body:
            children = self._extract_children(body)

        return ControlFlowNode(
            node_type="function",
            name=name,
            line=line,
            children=children,
        )

    def _extract_children(self, node: Node) -> list[ControlFlowNode]:
        """
        Recursively extract structural children from a tree-sitter node.

        Only nodes whose type is in ``_structural_types`` are included.
        Non-structural nodes are skipped, but their children are still explored.
        """
        result: list[ControlFlowNode] = []

        for child in node.children:
            ts_type = child.type
            if ts_type in self._structural_types and ts_type not in self._function_types:
                mapped_type = self._node_type_map[ts_type]
                name = self._get_call_name(child) if mapped_type == "function_call" else None
                line = child.start_point[0] + 1

                # Recurse into the structural node's body to find nested structures.
                nested = self._extract_children(child)

                cf_node = ControlFlowNode(
                    node_type=mapped_type,  # type: ignore[arg-type]
                    name=name,
                    line=line,
                    children=nested,
                )
                result.append(cf_node)
            else:
                # Not a structural node itself, but might contain structural children.
                result.extend(self._extract_children(child))

        return result

    # ─────────────────────────────────────────────────────────────────────────
    # Helper methods
    # ─────────────────────────────────────────────────────────────────────────

    def _get_function_name(self, node: Node) -> str:
        """Extract the function/method name from a definition node."""
        if self.language == "c":
            # C: function_definition > function_declarator > identifier
            declarator = self._find_child_by_type(node, "function_declarator")
            if declarator:
                ident = self._find_child_by_type(declarator, "identifier")
                if ident:
                    return ident.text.decode("utf-8") if ident.text else "<unknown>"
            # Fallback: pointer_declarator wrapping function_declarator
            ptr_decl = self._find_child_by_type(node, "pointer_declarator")
            if ptr_decl:
                return self._get_function_name_from_subtree(ptr_decl)
        else:
            # Java: method_declaration/constructor_declaration > identifier (name field)
            ident = self._find_child_by_field(node, "name")
            if ident:
                return ident.text.decode("utf-8") if ident.text else "<unknown>"

        return "<unknown>"

    def _get_function_name_from_subtree(self, node: Node) -> str:
        """Dig into nested declarators to find the function name."""
        func_decl = self._find_child_by_type(node, "function_declarator")
        if func_decl:
            ident = self._find_child_by_type(func_decl, "identifier")
            if ident and ident.text:
                return ident.text.decode("utf-8")
        return "<unknown>"

    def _get_call_name(self, node: Node) -> str | None:
        """Extract the callee name from a call expression / method invocation."""
        if self.language == "c":
            # call_expression > function: identifier
            func = self._find_child_by_field(node, "function")
            if func and func.type == "identifier" and func.text:
                return func.text.decode("utf-8")
        else:
            # method_invocation > name: identifier
            name = self._find_child_by_field(node, "name")
            if name and name.text:
                return name.text.decode("utf-8")
        return None

    def _find_function_body(self, node: Node) -> Node | None:
        """Find the body/block node of a function/method."""
        return (
            self._find_child_by_type(node, "compound_statement")
            or self._find_child_by_field(node, "body")
            or self._find_child_by_type(node, "block")
        )

    @staticmethod
    def _find_child_by_type(node: Node, type_name: str) -> Node | None:
        """Find the first direct child with the given node type."""
        for child in node.children:
            if child.type == type_name:
                return child
        return None

    @staticmethod
    def _find_child_by_field(node: Node, field_name: str) -> Node | None:
        """Find a child node by its field name."""
        return node.child_by_field_name(field_name)
