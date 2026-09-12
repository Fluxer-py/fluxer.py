"""Static public-surface checks for the separately approved Phase 4 audit.

These inspect source without importing optional voice dependencies or contacting
Fluxer. Lint and Griffe rendering checks remain separate verification steps.
"""

import ast
from pathlib import Path

import pytest

PACKAGE = Path(__file__).parents[1] / "fluxer"
MODULES = sorted(
    path
    for path in PACKAGE.rglob("*.py")
    if not path.name.startswith("_") or path.name == "__init__.py"
)


def public_nodes(body):
    for node in body:
        if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
            yield node
            yield from public_nodes(node.body)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if not node.name.startswith("_") or node.name == "__init__":
                yield node


@pytest.mark.parametrize(
    "path", MODULES, ids=lambda path: str(path.relative_to(PACKAGE))
)
def test_public_source_docs_and_signatures(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    assert ast.get_docstring(tree), f"{path}: missing module documentation"
    for node in public_nodes(tree.body):
        doc = ast.get_docstring(node)
        assert doc and len(doc.strip().splitlines()) > 1, (
            f"{node.name}: needs multiline documentation"
        )
        if isinstance(node, ast.ClassDef):
            assert "Attributes:" in doc, f"{node.name}: missing Attributes section"
            continue
        assert node.returns is not None, f"{node.name}: missing return annotation"
        parameters = [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]
        parameters += [
            arg for arg in (node.args.vararg, node.args.kwarg) if arg is not None
        ]
        for parameter in parameters:
            if parameter.arg not in {"self", "cls"}:
                assert parameter.annotation is not None, (
                    f"{node.name}.{parameter.arg}: missing annotation"
                )
        for item in ast.walk(node):
            if isinstance(item, ast.Subscript) and isinstance(item.value, ast.Name):
                assert item.value.id not in {
                    "Optional",
                    "Union",
                    "List",
                    "Dict",
                    "Tuple",
                    "Set",
                }, f"{node.name}: legacy generic annotation"


@pytest.mark.parametrize(
    "path", MODULES, ids=lambda path: str(path.relative_to(PACKAGE))
)
def test_public_instance_attributes_have_annotations(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for cls in (
        node for node in public_nodes(tree.body) if isinstance(node, ast.ClassDef)
    ):
        annotated = {
            node.target.id
            for node in cls.body
            if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name)
        }
        properties = {
            node.name
            for node in cls.body
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
            and any(
                isinstance(decorator, ast.Name) and decorator.id == "property"
                for decorator in node.decorator_list
            )
        }
        for node in ast.walk(cls):
            if isinstance(node, ast.AnnAssign) and isinstance(
                node.target, ast.Attribute
            ):
                if (
                    isinstance(node.target.value, ast.Name)
                    and node.target.value.id == "self"
                ):
                    annotated.add(node.target.attr)
        for node in ast.walk(cls):
            if not isinstance(node, ast.Assign):
                continue
            for target in node.targets:
                if isinstance(target, ast.Attribute) and isinstance(
                    target.value, ast.Name
                ):
                    if target.value.id == "self" and not target.attr.startswith("_"):
                        assert target.attr in annotated | properties, (
                            f"{cls.name}.{target.attr}: missing annotation"
                        )
