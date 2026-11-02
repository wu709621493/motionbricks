"""Static call inventory; not a traced/operator-complete execution graph."""
import ast
import json
from pathlib import Path
root = Path(__file__).resolve().parents[2]
files = {}
for path in sorted((root / 'tools/onnx').rglob('*.py')):
    tree = ast.parse(path.read_text())
    aliases = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name == 'torch': aliases[alias.asname or alias.name] = alias.name
        elif isinstance(node, ast.ImportFrom) and node.module and node.module.startswith('torch'):
            for alias in node.names: aliases[alias.asname or alias.name] = node.module+'.'+alias.name
    calls = []
    for node in ast.walk(tree):
        if not isinstance(node,ast.Call): continue
        name = ast.unparse(node.func)
        prefix = name.split('.')[0]
        if prefix in aliases:
            calls.append({'line':node.lineno,'call':aliases[prefix]+name[len(prefix):]})
    if calls: files[str(path.relative_to(root))] = sorted(calls,key=lambda x:x['line'])
print(json.dumps({'scope':'Static direct torch calls, including constructors and utilities; tensor methods, operators, alias flow and checkpoint-specific paths require manual audit.','files':files},indent=2))
