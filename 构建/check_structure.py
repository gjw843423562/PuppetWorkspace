"""只读检查目录归属、源码编码、导入与既有代码体积；不扫描技能仓库。"""
import ast
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FOLDERS = ("源码", "配置", "资源", "构建", "测试", "文档", "运行数据", "发布", "skill-repos", "tools")
ROOT_FILES = {"README.md", "AGENTS.md", ".editorconfig", ".gitignore", "pyproject.toml", "PuppetWorkspace.lnk", "启动工作区.cmd", "启动快捷键工具.cmd"}
COMPATIBILITY = {"_bootstrap.py", "puppet_workspace.py", "puppet_workspace.cmd", "puppet_workspace_ui.cmd", "puppet_workspace_ui.vbs", "build_exe.cmd"}


def check_root(errors):
    for path in ROOT.iterdir():
        if path.name.startswith(".") and path.is_dir():
            continue
        if path.is_dir() and path.name not in FOLDERS:
            if any(path.iterdir()):
                errors.append("未登记的根目录: " + path.name)
        elif path.is_file() and path.name not in ROOT_FILES:
            errors.append("根目录散落文件: " + path.name)
    for path in (ROOT / "tools").glob("*"):
        if path.name == "__pycache__":
            continue
        if path.name not in COMPATIBILITY:
            errors.append("旧入口层混入实现或产物: " + str(path.relative_to(ROOT)))


def check_functions(tree, baseline, name, errors):
    old = baseline.get(name, {}).get("long_functions", {})
    # 以函数名匹配，允许修改上方 import 导致行号变化。
    limits = {key.split(":", 1)[1]: size for key, size in old.items()}
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            length = node.end_lineno - node.lineno + 1
            if length > max(40, limits.get(node.name, 40)):
                errors.append("函数超过体积约定: %s:%d %s" % (name, node.lineno, node.name))


def check_python(path, baseline, errors):
    name = path.relative_to(ROOT).as_posix()
    raw = path.read_bytes()
    if b"\r\n" in raw or raw.startswith(b"\xef\xbb\xbf") or not raw.endswith(b"\n"):
        errors.append("编码/换行不统一: " + name)
    try:
        text = raw.decode("utf-8")
        tree = ast.parse(text, filename=name)
    except (UnicodeError, SyntaxError) as exc:
        errors.append(str(exc))
        return
    limit = max(500, baseline.get(name, {}).get("lines", 500))
    if len(text.splitlines()) > min(limit, 800):
        errors.append("文件超过体积约定: " + name)
    if "/puppet_" in name and ("sys.path.insert" in text or "sys.path.append" in text):
        errors.append("业务模块不得改写 sys.path: " + name)
    check_functions(tree, baseline, name, errors)


def main():
    errors = []
    baseline = json.loads((ROOT / "构建/结构基线.json").read_text(encoding="utf-8"))
    check_root(errors)
    files = [path for folder in ("源码", "构建", "测试") for path in (ROOT / folder).rglob("*.py")]
    for path in files:
        check_python(path, baseline, errors)
    if errors:
        print("\n".join(errors))
        return 1
    print("结构检查通过：%d 个 Python 文件；目录、UTF-8/LF、语法、业务路径及体积基线" % len(files))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
