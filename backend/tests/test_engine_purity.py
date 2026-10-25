import ast
from pathlib import Path

FORBIDDEN = {"fastapi", "sqlalchemy", "app", "httpx", "requests", "paypalrestsdk", "pydantic"}


def test_engine_modules_import_no_framework_db_or_payment_code():
    for f in (Path(__file__).resolve().parent.parent / "financial_engine").glob("*.py"):
        for node in ast.walk(ast.parse(f.read_text())):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name.split(".")[0] for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                names = [node.module.split(".")[0]]
            assert not (set(names) & FORBIDDEN), f"{f.name} imports {names}"
