"""
Tree-sitter S-expression query patterns for Java structural elements.

These queries are used by the StructuralExtractor to identify
control-flow structures in Java source code. Each query returns
tagged captures that map to ControlFlowNode types.

Reference: https://github.com/tree-sitter/tree-sitter-java/blob/master/src/node-types.json
"""

# ─── Methods ───────────────────────────────────────────────────────────────────
METHOD_QUERY = """
(method_declaration
  name: (identifier) @method.name
) @method.def
"""

# Constructor is also a "function" in our unified model.
CONSTRUCTOR_QUERY = """
(constructor_declaration
  name: (identifier) @ctor.name
) @ctor.def
"""

# ─── Loops ─────────────────────────────────────────────────────────────────────
FOR_LOOP_QUERY = "(for_statement) @loop.for"
ENHANCED_FOR_QUERY = "(enhanced_for_statement) @loop.for"  # for-each → maps to for_loop
WHILE_LOOP_QUERY = "(while_statement) @loop.while"
DO_WHILE_QUERY = "(do_statement) @loop.do_while"

# ─── Branches ──────────────────────────────────────────────────────────────────
IF_QUERY = "(if_statement) @branch.if"
SWITCH_QUERY = "(switch_expression) @branch.switch"
CASE_QUERY = "(switch_label) @branch.case"

# ─── Returns ───────────────────────────────────────────────────────────────────
RETURN_QUERY = "(return_statement) @stmt.return"

# ─── Method calls ─────────────────────────────────────────────────────────────
CALL_QUERY = """
(method_invocation
  name: (identifier) @call.name
) @call.expr
"""

# ─── Try-catch (Java-specific) ─────────────────────────────────────────────────
TRY_CATCH_QUERY = "(try_statement) @stmt.try_catch"

# ─── Node type name mapping ───────────────────────────────────────────────────
# Maps tree-sitter Java node type names to our unified NodeType vocabulary.
NODE_TYPE_MAP: dict[str, str] = {
    "method_declaration": "function",
    "constructor_declaration": "function",
    "for_statement": "for_loop",
    "enhanced_for_statement": "for_loop",  # for-each maps to for_loop
    "while_statement": "while_loop",
    "do_statement": "do_while_loop",
    "if_statement": "if_branch",
    "switch_expression": "switch",
    "switch_label": "case",
    "return_statement": "return",
    "method_invocation": "function_call",
    "try_statement": "try_catch",
}

# Set of tree-sitter node types we consider "structural" (control-flow relevant).
STRUCTURAL_NODE_TYPES: set[str] = set(NODE_TYPE_MAP.keys())
