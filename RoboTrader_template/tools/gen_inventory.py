"""연구 디렉토리(scripts/, multiverse/, backtest/) 인벤토리 생성 — AST import 그래프 기반.

분류:
  LIVE-DEP   : 운영 디렉토리 파일이 import (Phase1 이후 0이어야 정상)
  TEST-ONLY  : tests/ 만 import
  RESEARCH   : 연구 파일끼리만 import
  UNREFERENCED: 어디서도 import 안 됨 (죽음 후보 — 단, 동적 import/CLI 직접실행은 수동확인)
사용: venv\\Scripts\\python tools/gen_inventory.py > docs/INVENTORY.md
"""
import ast
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROD_DIRS = ["core", "bot", "framework", "api", "strategies", "collectors",
             "db", "runners", "signals", "lib", "utils", "tools", "config"]
RESEARCH_DIRS = ["scripts", "multiverse", "backtest"]
SKIP_DIRS = {"__pycache__", "venv", "venv_broken_quantcopy", ".git", "logs", "reports"}


def iter_py(dirs):
    for d in dirs:
        base = os.path.join(ROOT, d)
        if not os.path.isdir(base):
            continue
        for dirpath, dirnames, filenames in os.walk(base):
            dirnames[:] = [x for x in dirnames if x not in SKIP_DIRS]
            for f in filenames:
                if f.endswith(".py"):
                    yield os.path.relpath(os.path.join(dirpath, f), ROOT)


def module_name(relpath):
    return relpath[:-3].replace(os.sep, ".").replace("/", ".")


def imports_of_source(text):
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return set()
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            mods.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            mods.add(node.module)
            for a in node.names:  # from pkg import module 케이스 포착
                mods.add(f"{node.module}.{a.name}")
        elif isinstance(node, ast.Call):
            # importlib.import_module("...") / __import__("...") 리터럴 인자 포착
            fn = node.func
            name = (getattr(fn, "attr", "") or getattr(fn, "id", ""))
            if name in ("import_module", "__import__") and node.args \
                    and isinstance(node.args[0], ast.Constant) and isinstance(node.args[0].value, str):
                mods.add(node.args[0].value)
    return mods


def imports_of(relpath):
    try:
        with open(os.path.join(ROOT, relpath), encoding="utf-8") as fh:
            text = fh.read()
    except UnicodeDecodeError:
        return set()
    return imports_of_source(text)


def main():
    research = {module_name(p): p for p in iter_py(RESEARCH_DIRS)}
    referrers = {m: [] for m in research}  # research module -> [참조자 relpath]
    for scope, dirs in (("PROD", PROD_DIRS), ("TEST", ["tests"]), ("RESEARCH", RESEARCH_DIRS)):
        for p in iter_py(dirs):
            for m in imports_of(p):
                for rm in research:
                    if m == rm or m.startswith(rm + "."):
                        referrers[rm].append((scope, p))
    print("# INVENTORY — 연구 파일 참조 태깅 (tools/gen_inventory.py 생성)\n")
    print("| 파일 | 태그 | 참조자 |")
    print("|---|---|---|")
    for rm, path in sorted(research.items()):
        refs = [r for r in referrers[rm] if r[1] != path]
        scopes = {s for s, _ in refs}
        tag = ("LIVE-DEP" if "PROD" in scopes else
               "TEST-ONLY" if scopes == {"TEST"} else
               "RESEARCH" if scopes else "UNREFERENCED")
        ref_str = "; ".join(f"{s}:{p}" for s, p in sorted(set(refs))[:5]) or "-"
        print(f"| `{path}` | {tag} | {ref_str} |")


if __name__ == "__main__":
    main()
