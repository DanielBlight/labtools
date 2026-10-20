"""Repair misplaced settings-save block without changing map or hardware logic."""
import ast
from datetime import datetime
from pathlib import Path

PATH = Path("src/labtools/gui/intensity_map_gui.py")


def repair(source):
    tree = ast.parse(source)
    windows = [n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "IntensityMapWindow"]
    if len(windows) != 1:
        raise ValueError("Expected one IntensityMapWindow; file unchanged")
    window = windows[0]
    close = [n for n in window.body if isinstance(n, ast.FunctionDef) and n.name == "closeEvent"]
    if len(close) != 1:
        raise ValueError("Expected one closeEvent; file unchanged")
    close = close[0]
    misplaced = []
    for method in window.body:
        if not isinstance(method, ast.FunctionDef) or method.name == "closeEvent":
            continue
        for node in ast.walk(method):
            if isinstance(node, ast.If) and ast.unparse(node.test) == "event.isAccepted()":
                if node.orelse or len(node.body) != 1 or ast.unparse(node.body[0]) != "self._save_map_preferences()":
                    raise ValueError("Unexpected event block; file unchanged")
                misplaced.append(node)
    if not misplaced:
        raise ValueError("No misplaced settings-save block found; file unchanged")
    edits = [(n.lineno - 1, n.end_lineno, "") for n in misplaced]
    saves = [n for n in ast.walk(close) if isinstance(n, ast.Call) and ast.unparse(n.func) == "self._save_map_preferences"]
    if not saves:
        endings = [n for n in close.body if isinstance(n, ast.Expr) and isinstance(n.value, ast.Call) and ast.unparse(n.value.func) == "super().closeEvent"]
        if len(endings) != 1:
            raise ValueError("Cannot identify accepted close path; file unchanged")
        at = endings[0].end_lineno
        edits.append((at, at, "        if event.isAccepted():\n            self._save_map_preferences()\n"))
    lines = source.splitlines(keepends=True)
    for start, end, replacement in sorted(edits, reverse=True):
        lines[start:end] = [replacement]
    result = "".join(lines)
    compile(result, str(PATH), "exec")
    # Check the scope, not just syntax.
    fixed = ast.parse(result)
    cls = next(n for n in fixed.body if isinstance(n, ast.ClassDef) and n.name == window.name)
    for method in cls.body:
        if isinstance(method, ast.FunctionDef) and method.name != "closeEvent":
            if any(isinstance(n, ast.Call) and ast.unparse(n.func) == "self._save_map_preferences" for n in ast.walk(method)):
                raise ValueError("Save call remains outside closeEvent; file unchanged")
    return result


def main():
    original = PATH.read_bytes()
    updated = repair(original.decode("utf-8-sig"))
    backup = PATH.with_name(PATH.name + ".before-save-scope-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f") + ".bak")
    backup.write_bytes(original)
    try:
        PATH.write_text(updated, encoding="utf-8")
    except Exception:
        PATH.write_bytes(original)
        raise
    print("[OK] Moved settings saving into closeEvent.")
    print(f"Backup: {backup}")


if __name__ == "__main__":
    main()
