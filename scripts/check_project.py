"""检查独立仓库结构、文档链接、测试和命名JSON命令入口。"""
from __future__ import annotations

import argparse
import ast
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys


def repository_root():
    """以分发元数据和计算包为标记，不依赖宿主路径或启动目录。"""
    for directory in Path(__file__).resolve().parents:
        if (directory / "pyproject.toml").is_file() and (directory / "gear_contact").is_dir():
            return directory
    raise RuntimeError("没有找到包含pyproject.toml与gear_contact的项目根目录")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-tests", action="store_true", help="其他步骤已执行测试时只检查项目和命令入口")
    args = parser.parse_args()
    root = repository_root()
    output = root / "output"
    output.mkdir(exist_ok=True)
    environment = dict(os.environ)
    environment.update(PYTHONUTF8="1", PYTHONIOENCODING="utf-8", PYTHONDONTWRITEBYTECODE="1",
                       MPLCONFIGDIR=str(root / ".cache" / "matplotlib"))
    required = ("README.md", "README.en.md", "LICENSE", "pyproject.toml", "constraints.txt", "MANIFEST.in", ".gitignore",
                ".github/workflows/ci.yml", "examples/spur_case.json", "examples/run_examples.py",
                "docs/model.md", "docs/api.md", "docs/validation.md")
    missing = [name for name in required if not (root / name).is_file()]
    if missing:
        raise RuntimeError("缺少仓库文件：" + ", ".join(missing))
    source_files = [path for folder in ("gear_contact", "examples", "tests", "scripts")
                    for path in (root / folder).rglob("*.py") if "__pycache__" not in path.parts]
    for path in source_files:
        ast.parse(path.read_text(encoding="utf-8-sig"), filename=path.relative_to(root).as_posix())
    broken_links = []
    documents = [root / name for name in ("README.md", "README.en.md", "CHANGELOG.md", "CONTRIBUTING.md")]
    documents.extend((root / "docs").rglob("*.md"))
    for document in documents:
        body = document.read_text(encoding="utf-8")
        for target in re.findall(r"!?\[[^\]]*\]\(([^)]+)\)", body):
            target = target.split("#", 1)[0]
            if target and not re.match(r"[a-zA-Z][a-zA-Z0-9+.-]*:", target):
                if not (document.parent / target).exists():
                    broken_links.append(document.relative_to(root).as_posix() + " → " + target)
    if broken_links:
        raise RuntimeError("文档相对链接失效：" + "; ".join(broken_links))

    test_count = None
    if not args.skip_tests:
        completed = subprocess.run([sys.executable, "-B", "-m", "unittest", "discover", "-s", "tests", "-v"],
                                   cwd=root, env=environment, capture_output=True, text=True,
                                   encoding="utf-8", errors="replace")
        (output / "unit_tests.txt").write_text(completed.stdout + completed.stderr, encoding="utf-8")
        if completed.returncode:
            raise RuntimeError("测试失败，请查看output/unit_tests.txt")
        match = re.search(r"Ran (\d+) tests", completed.stderr)
        test_count = int(match.group(1)) if match else None

    configuration = json.loads((root / "examples/spur_case.json").read_text(encoding="utf-8"))
    configuration.update(phases=4, strips=5)
    smoke_input = output / "check_input.json"
    smoke_input.write_text(json.dumps(configuration, ensure_ascii=False, indent=2), encoding="utf-8")
    completed = subprocess.run([sys.executable, "-B", "-m", "gear_contact", str(smoke_input),
                                "--output", str(output / "check_case")], cwd=root, env=environment,
                               capture_output=True, text=True, encoding="utf-8", errors="replace")
    if completed.returncode:
        raise RuntimeError("命令入口计算失败：" + completed.stderr)
    summary = json.loads((output / "check_case/summary.json").read_text(encoding="utf-8"))
    if (not summary["all_converged"] or summary["max_force_residual_n"] > 1e-8
            or summary["max_gap_residual_m"] > 3e-12):
        raise RuntimeError("命令计算未满足声明的力与间隙残差要求")
    record = {
        "checked_at_utc": datetime.now(timezone.utc).isoformat(),
        "required_files_passed": True,
        "python_syntax_passed": True,
        "relative_document_links_passed": True,
        "unit_tests_passed": not args.skip_tests,
        "unit_test_count": test_count,
        "unit_tests_skipped": args.skip_tests,
        "json_cli_passed": True,
        "force_residual_n": summary["max_force_residual_n"],
        "gap_residual_m": summary["max_gap_residual_m"],
        "python": sys.version.split()[0],
        "source_sha256": {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
                          for path in source_files},
    }
    (output / "project_check.json").write_text(json.dumps(record, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"项目检查": "通过", "单元测试数量": test_count,
                      "命令计算": "通过", "报告": "output/project_check.json"}, ensure_ascii=False))


if __name__ == "__main__":
    main()
