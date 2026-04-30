"""
Tests for enjinc.ast_audit — AST Edit Distance Audit module.

Covers all public functions:
  - parse_python_ast
  - parse_java_ast
  - compute_edit_distance
  - audit_code
"""

import pytest

from enjinc.ast_audit import (
    ASTNode,
    AuditResult,
    EditDistance,
    audit_code,
    compute_edit_distance,
    parse_java_ast,
    parse_python_ast,
)


# ============================================================
# TestParsePythonAst
# ============================================================


class TestParsePythonAst:
    """Tests for parse_python_ast()."""

    def test_parse_function(self):
        """Parse a simple Python function and verify ASTNode with correct type and name."""
        code = (
            "def greet(name: str) -> str:\n"
            "    return f'Hello {name}'\n"
        )
        nodes = parse_python_ast(code)

        assert len(nodes) == 1
        func = nodes[0]
        assert isinstance(func, ASTNode)
        assert func.node_type == "function"
        assert func.name == "greet"
        # Tokens should contain identifiers from the function body and signature
        assert "name" in func.tokens
        assert "str" in func.tokens
        assert func.children == []

    def test_parse_class(self):
        """Parse a class with methods and verify class node has method children."""
        code = (
            "class UserService:\n"
            "    def __init__(self, db_url: str):\n"
            "        self.db_url = db_url\n"
            "\n"
            "    def get_user(self, user_id: int) -> dict:\n"
            "        return {'id': user_id}\n"
        )
        nodes = parse_python_ast(code)

        assert len(nodes) == 1
        cls = nodes[0]
        assert cls.node_type == "class"
        assert cls.name == "UserService"
        # Should have two method children
        assert len(cls.children) == 2
        method_names = {c.name for c in cls.children}
        assert "__init__" in method_names
        assert "get_user" in method_names

    def test_parse_imports(self):
        """Verify import nodes are extracted with correct type and tokens."""
        code = (
            "import os\n"
            "import sys\n"
            "from typing import List, Optional\n"
        )
        nodes = parse_python_ast(code)

        # Each import statement produces its own node
        assert len(nodes) == 3
        import_types = {n.node_type for n in nodes}
        assert import_types == {"import"}

        # Check that import names are captured
        names = {n.name for n in nodes}
        assert "os" in names
        assert "sys" in names
        assert "typing" in names  # from ... import yields module name

        # Check that imported symbols are in tokens
        typing_node = next(n for n in nodes if n.name == "typing")
        assert "List" in typing_node.tokens
        assert "Optional" in typing_node.tokens

    def test_parse_empty_code(self):
        """Empty string should return an empty list."""
        nodes = parse_python_ast("")
        assert nodes == []

    def test_parse_syntax_error_returns_empty(self):
        """Syntax errors should return an empty list, not raise."""
        nodes = parse_python_ast("def foo(")
        assert nodes == []


# ============================================================
# TestParseJavaAst
# ============================================================


class TestParseJavaAst:
    """Tests for parse_java_ast()."""

    def test_parse_method(self):
        """Parse a Java method and verify extraction of method node."""
        code = (
            "public class Calculator {\n"
            "    public int add(int a, int b) {\n"
            "        return a + b;\n"
            "    }\n"
            "}\n"
        )
        nodes = parse_java_ast(code)

        # Should find the class with a method child
        assert len(nodes) >= 1
        cls_node = next((n for n in nodes if n.node_type == "class"), None)
        assert cls_node is not None
        assert cls_node.name == "Calculator"
        assert len(cls_node.children) >= 1

        method = cls_node.children[0]
        assert method.node_type == "method"
        assert method.name == "add"

    def test_parse_class(self):
        """Parse a Java class with multiple methods."""
        code = (
            "public class UserService {\n"
            "    public User getUser(int id) {\n"
            "        return userRepository.findById(id);\n"
            "    }\n"
            "\n"
            "    public void deleteUser(int id) {\n"
            "        userRepository.deleteById(id);\n"
            "    }\n"
            "}\n"
        )
        nodes = parse_java_ast(code)

        cls_node = next((n for n in nodes if n.node_type == "class"), None)
        assert cls_node is not None
        assert cls_node.name == "UserService"

        method_names = {c.name for c in cls_node.children}
        assert "getUser" in method_names
        assert "deleteUser" in method_names

    def test_parse_empty_code(self):
        """Empty string should return an empty list."""
        nodes = parse_java_ast("")
        assert nodes == []

    def test_parse_imports(self):
        """Parse Java imports and verify they are captured."""
        code = (
            "import java.util.List;\n"
            "import java.util.ArrayList;\n"
            "import java.io.*;\n"
            "\n"
            "public class App {}\n"
        )
        nodes = parse_java_ast(code)

        import_node = next((n for n in nodes if n.node_type == "import"), None)
        assert import_node is not None
        assert "java.util.List" in import_node.tokens
        assert "java.util.ArrayList" in import_node.tokens

    def test_parse_standalone_methods(self):
        """When no class is present, methods should still be extracted at top level."""
        code = (
            "public void standalone() {\n"
            "    System.out.println(\"hello\");\n"
            "}\n"
        )
        nodes = parse_java_ast(code)

        # No class match, so methods should appear as top-level nodes
        assert len(nodes) >= 1
        method = next((n for n in nodes if n.node_type == "method"), None)
        assert method is not None
        assert method.name == "standalone"


# ============================================================
# TestComputeEditDistance
# ============================================================


class TestComputeEditDistance:
    """Tests for compute_edit_distance()."""

    def test_identical_code(self):
        """Same code → distance 0.0, no added/removed/modified nodes."""
        nodes = [
            ASTNode(node_type="function", name="foo", tokens={"x", "y", "return"}),
            ASTNode(node_type="function", name="bar", tokens={"a", "b"}),
        ]
        result = compute_edit_distance(nodes, nodes)

        assert isinstance(result, EditDistance)
        assert result.total_distance == 0.0
        assert result.added_nodes == []
        assert result.removed_nodes == []
        assert result.modified_nodes == []

    def test_added_function(self):
        """New code has an extra function → added_nodes should be non-empty."""
        old_nodes = [
            ASTNode(node_type="function", name="foo", tokens={"x"}),
        ]
        new_nodes = [
            ASTNode(node_type="function", name="foo", tokens={"x"}),
            ASTNode(node_type="function", name="bar", tokens={"y"}),
        ]
        result = compute_edit_distance(old_nodes, new_nodes)

        assert len(result.added_nodes) == 1
        assert "bar" in result.added_nodes
        assert result.removed_nodes == []

    def test_removed_function(self):
        """New code is missing a function → removed_nodes should be non-empty."""
        old_nodes = [
            ASTNode(node_type="function", name="foo", tokens={"x"}),
            ASTNode(node_type="function", name="bar", tokens={"y"}),
        ]
        new_nodes = [
            ASTNode(node_type="function", name="foo", tokens={"x"}),
        ]
        result = compute_edit_distance(old_nodes, new_nodes)

        assert len(result.removed_nodes) == 1
        assert "bar" in result.removed_nodes
        assert result.added_nodes == []

    def test_modified_function(self):
        """Same function name but different tokens → modified_nodes with similarity < 1.0."""
        old_nodes = [
            ASTNode(node_type="function", name="process", tokens={"alpha", "beta", "gamma"}),
        ]
        new_nodes = [
            ASTNode(node_type="function", name="process", tokens={"alpha", "delta", "epsilon"}),
        ]
        result = compute_edit_distance(old_nodes, new_nodes)

        assert len(result.modified_nodes) >= 1
        # The first modified entry should be for the "process" node
        qualified_name, similarity = result.modified_nodes[0]
        assert "process" in qualified_name
        assert 0.0 < similarity < 1.0

    def test_both_empty(self):
        """Two empty lists should produce zero distance."""
        result = compute_edit_distance([], [])
        assert result.total_distance == 0.0
        assert result.added_nodes == []
        assert result.removed_nodes == []
        assert result.modified_nodes == []

    def test_class_with_modified_child(self):
        """Modifications to class children (methods) are tracked."""
        old_nodes = [
            ASTNode(
                node_type="class",
                name="Service",
                children=[
                    ASTNode(node_type="function", name="run", tokens={"old_token"}),
                ],
                tokens=set(),
            ),
        ]
        new_nodes = [
            ASTNode(
                node_type="class",
                name="Service",
                children=[
                    ASTNode(node_type="function", name="run", tokens={"new_token"}),
                ],
                tokens=set(),
            ),
        ]
        result = compute_edit_distance(old_nodes, new_nodes)

        # The class node itself is modified (its children differ)
        assert len(result.modified_nodes) >= 1
        # Check that total_distance > 0
        assert result.total_distance > 0.0


# ============================================================
# TestAuditCode
# ============================================================


class TestAuditCode:
    """Tests for audit_code()."""

    def test_audit_passes_for_similar_code(self):
        """Slightly modified code should pass with a lenient threshold (0.5)."""
        old_code = (
            "def greet(name: str) -> str:\n"
            "    message = f'Hello {name}'\n"
            "    return message\n"
        )
        # Same function with a minor token change
        new_code = (
            "def greet(name: str) -> str:\n"
            "    greeting = f'Hello {name}'\n"
            "    return greeting\n"
        )
        result = audit_code(old_code, new_code, lang="python", threshold=0.5)

        assert isinstance(result, AuditResult)
        # With a low threshold of 0.5, similar code should pass
        assert result.passed is True
        assert result.blocked_nodes == []

    def test_audit_fails_for_major_changes(self):
        """Completely different code should fail audit (blocked or removed nodes)."""
        old_code = (
            "def fetch_data(url: str) -> dict:\n"
            "    response = requests.get(url)\n"
            "    return response.json()\n"
        )
        new_code = (
            "def process_items(items: list) -> int:\n"
            "    total = sum(item.value for item in items)\n"
            "    return total\n"
        )
        result = audit_code(old_code, new_code, lang="python", threshold=0.7)

        # The old function "fetch_data" is removed, new one "process_items" added
        assert result.passed is False

    def test_audit_with_different_thresholds(self):
        """Verify that threshold parameter controls pass/fail boundary."""
        old_code = (
            "def compute(x: int, y: int) -> int:\n"
            "    result = x + y\n"
            "    return result\n"
        )
        # Partially different: same function name, some shared tokens, some new
        new_code = (
            "def compute(x: int, y: int) -> int:\n"
            "    value = x * y\n"
            "    return value\n"
        )

        # With a very lenient threshold, it should pass
        result_lenient = audit_code(old_code, new_code, lang="python", threshold=0.1)
        assert result_lenient.passed is True

        # With a very strict threshold, it should fail
        result_strict = audit_code(old_code, new_code, lang="python", threshold=0.99)
        assert result_strict.passed is False

    def test_audit_identical_code_passes(self):
        """Identical code should always pass."""
        code = (
            "def hello():\n"
            "    print('world')\n"
        )
        result = audit_code(code, code, lang="python")
        assert result.passed is True
        assert result.blocked_nodes == []
        assert result.distance.total_distance == 0.0

    def test_audit_java_language(self):
        """Audit should work with Java language parameter."""
        old_code = (
            "public class Service {\n"
            "    public void execute() {\n"
            "        System.out.println(\"hello\");\n"
            "    }\n"
            "}\n"
        )
        new_code = (
            "public class Service {\n"
            "    public void execute() {\n"
            "        System.out.println(\"world\");\n"
            "    }\n"
            "}\n"
        )
        result = audit_code(old_code, new_code, lang="java", threshold=0.3)
        assert isinstance(result, AuditResult)

    def test_audit_unsupported_language(self):
        """Unsupported language should return failed result with warning."""
        result = audit_code("x = 1", "x = 2", lang="rust")
        assert result.passed is False
        assert any("Unsupported language" in w for w in result.warnings)

    def test_audit_removed_node_causes_failure(self):
        """Removed nodes should cause audit to fail (even if no blocked nodes)."""
        old_code = (
            "def foo():\n"
            "    pass\n"
            "\n"
            "def bar():\n"
            "    pass\n"
        )
        new_code = (
            "def foo():\n"
            "    pass\n"
        )
        result = audit_code(old_code, new_code, lang="python", threshold=0.7)

        # "bar" is removed, so audit should fail
        assert result.passed is False
        assert any("removed" in w.lower() for w in result.warnings)
