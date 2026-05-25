"""
Tree-sitter S-expression query patterns for C structural elements.

These queries are used by the StructuralExtractor to identify
control-flow structures in C source code. Each query returns
tagged captures that map to ControlFlowNode types.

Reference: https://github.com/tree-sitter/tree-sitter-c/blob/master/src/node-types.json
"""

# ─── Functions ─────────────────────────────────────────────────────────────────
FUNCTION_QUERY = """
(function_definition
  declarator: (function_declarator
    declarator: (identifier) @func.name)
) @func.def
"""

# ─── Loops ─────────────────────────────────────────────────────────────────────
FOR_LOOP_QUERY = "(for_statement) @loop.for"
WHILE_LOOP_QUERY = "(while_statement) @loop.while"
DO_WHILE_QUERY = "(do_statement) @loop.do_while"

# ─── Branches ──────────────────────────────────────────────────────────────────
IF_QUERY = "(if_statement) @branch.if"
SWITCH_QUERY = "(switch_statement) @branch.switch"
CASE_QUERY = "(case_statement) @branch.case"

# ─── Returns ───────────────────────────────────────────────────────────────────
RETURN_QUERY = "(return_statement) @stmt.return"

# ─── Function calls ───────────────────────────────────────────────────────────
CALL_QUERY = """
(call_expression
  function: (identifier) @call.name
) @call.expr
"""

# ─── Node type name mapping ───────────────────────────────────────────────────
# Maps tree-sitter C node type names to our unified NodeType vocabulary.
NODE_TYPE_MAP: dict[str, str] = {
    "function_definition": "function",
    "for_statement": "for_loop",
    "while_statement": "while_loop",
    "do_statement": "do_while_loop",
    "if_statement": "if_branch",
    "switch_statement": "switch",
    "case_statement": "case",
    "return_statement": "return",
    "call_expression": "function_call",
}

# Set of tree-sitter node types we consider "structural" (control-flow relevant).
STRUCTURAL_NODE_TYPES: set[str] = set(NODE_TYPE_MAP.keys())
