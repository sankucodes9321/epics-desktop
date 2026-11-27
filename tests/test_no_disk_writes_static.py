"""Conservative source guard for direct sinks and common array aliases."""
import ast
from pathlib import Path


def violations(source):
    tree = ast.parse(source)
    aliases = {}
    sensitive = {"frame", "crop", "vector", "matrix", "gray", "edges", "scratch",
                 "region", "array", "embedding", "values", "key", "plaintext", "faces"}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            aliases.update({x.asname or x.name: x.name for x in node.names})
        if isinstance(node, ast.ImportFrom):
            aliases.update({x.asname or x.name: f"{node.module}.{x.name}" for x in node.names})
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Name):
            if node.value.id in sensitive:
                sensitive.update(t.id for t in node.targets if isinstance(t, ast.Name))
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)) and "tempfile" in ast.unparse(node):
            yield node.lineno
        if not isinstance(node, ast.Call):
            continue
        target = ast.unparse(node.func).split(".")
        name = ".".join([aliases.get(target[0], target[0]), *target[1:]])
        if name in {"cv2.imwrite", "cv2.imencode", "numpy.save", "pickle.dump"} or name.endswith(".tofile"):
            yield node.lineno
        if target[-1] in {"print", "info", "debug", "warning", "error", "exception", "critical", "log"}:
            if any(isinstance(t, ast.Name) and t.id in sensitive for arg in node.args for t in ast.walk(arg)):
                yield node.lineno


def test_privacy_sources():
    root = Path(__file__).resolve().parents[1] / "privacy"
    assert not [(p.name, line) for p in root.rglob("*.py") for line in violations(p.read_text())]
