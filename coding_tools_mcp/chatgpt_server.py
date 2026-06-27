from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from . import server as _server


@dataclass(frozen=True)
class FixedTaskTool:
    title: str
    description: str
    cmd: str
    timeout_ms: int
    max_timeout_ms: int


FIXED_TASK_TOOLS: dict[str, FixedTaskTool] = {
    "run_vitest": FixedTaskTool(
        title="Run Vitest",
        description=(
            "Run the workspace's local Vitest test suite without exposing an arbitrary shell command argument."
        ),
        cmd="npx --no-install vitest run",
        timeout_ms=120_000,
        max_timeout_ms=300_000,
    ),
    "run_npm_test": FixedTaskTool(
        title="Run npm test",
        description="Run `npm test` in the workspace without exposing an arbitrary shell command argument.",
        cmd="npm test",
        timeout_ms=120_000,
        max_timeout_ms=300_000,
    ),
    "run_npm_typecheck": FixedTaskTool(
        title="Run npm typecheck",
        description=(
            "Run `npm run typecheck --if-present` in the workspace without exposing an arbitrary shell command argument."
        ),
        cmd="npm run typecheck --if-present",
        timeout_ms=120_000,
        max_timeout_ms=300_000,
    ),
    "run_npm_lint": FixedTaskTool(
        title="Run npm lint",
        description="Run `npm run lint --if-present` in the workspace without exposing an arbitrary shell command argument.",
        cmd="npm run lint --if-present",
        timeout_ms=120_000,
        max_timeout_ms=300_000,
    ),
    "run_npm_build": FixedTaskTool(
        title="Run npm build",
        description="Run `npm run build --if-present` in the workspace without exposing an arbitrary shell command argument.",
        cmd="npm run build --if-present",
        timeout_ms=180_000,
        max_timeout_ms=600_000,
    ),
    "run_npm_build_renderer": FixedTaskTool(
        title="Run npm renderer build",
        description=(
            "Run `npm run build:renderer --if-present` in the workspace without exposing an arbitrary shell command argument."
        ),
        cmd="npm run build:renderer --if-present",
        timeout_ms=180_000,
        max_timeout_ms=600_000,
    ),
    "run_npm_validate": FixedTaskTool(
        title="Run npm validate",
        description=(
            "Run `npm run validate --if-present` in the workspace without exposing an arbitrary shell command argument."
        ),
        cmd="npm run validate --if-present",
        timeout_ms=300_000,
        max_timeout_ms=600_000,
    ),
    "run_addon_validation": FixedTaskTool(
        title="Run addon validation",
        description=(
            "Run `npm run validate:addon --if-present` in the workspace without exposing an arbitrary shell command argument."
        ),
        cmd="npm run validate:addon --if-present",
        timeout_ms=120_000,
        max_timeout_ms=300_000,
    ),
    "run_npm_validate_addons": FixedTaskTool(
        title="Run npm addons validation",
        description=(
            "Run `npm run validate:addons --if-present` in the workspace without exposing an arbitrary shell command argument."
        ),
        cmd="npm run validate:addons --if-present",
        timeout_ms=120_000,
        max_timeout_ms=300_000,
    ),
    "run_python_tests": FixedTaskTool(
        title="Run Python tests",
        description=(
            "Run Python unittest discovery in the workspace without exposing an arbitrary shell command argument."
        ),
        cmd="python -m unittest discover -s tests -p 'test_*.py'",
        timeout_ms=120_000,
        max_timeout_ms=300_000,
    ),
    "run_make_test": FixedTaskTool(
        title="Run make test",
        description="Run `make test` in the workspace without exposing an arbitrary shell command argument.",
        cmd="make test",
        timeout_ms=120_000,
        max_timeout_ms=300_000,
    ),
    "run_make_ci": FixedTaskTool(
        title="Run make ci",
        description="Run `make ci` in the workspace without exposing an arbitrary shell command argument.",
        cmd="make ci",
        timeout_ms=300_000,
        max_timeout_ms=600_000,
    ),
    "run_make_compliance": FixedTaskTool(
        title="Run make compliance",
        description="Run `make compliance` in the workspace without exposing an arbitrary shell command argument.",
        cmd="make compliance",
        timeout_ms=300_000,
        max_timeout_ms=600_000,
    ),
}


_ORIGINAL_INPUT_SCHEMAS: Callable[[], dict[str, dict[str, Any]]] = _server.input_schemas
_PATCHED = False


LIST_PACKAGE_SCRIPTS_TOOL = "list_package_scripts"
REPLACE_TEXT_TOOL = "replace_text"


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def _task_input_schema(task: FixedTaskTool) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "workdir": {"type": "string", "default": "."},
            "timeout_ms": {
                "type": "integer",
                "minimum": 1,
                "maximum": task.max_timeout_ms,
                "default": task.timeout_ms,
            },
            "yield_time_ms": {"type": "integer", "minimum": 0, "maximum": 30000, "default": 1000},
            "max_output_bytes": {"type": "integer", "minimum": 1, "maximum": 1048576, "default": 65536},
        },
        "additionalProperties": False,
    }


def _list_package_scripts_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "path": {"type": "string", "default": "package.json"},
        },
        "additionalProperties": False,
    }


def _replace_text_input_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            "path": {"type": "string"},
            "old": {"type": "string"},
            "new": {"type": "string"},
            "expected_replacements": {"type": "integer", "minimum": 1, "default": 1},
            "dry_run": {"type": "boolean", "default": False},
        },
        "required": ["path", "old", "new"],
        "additionalProperties": False,
    }


def _input_schemas_with_chatgpt_tools() -> dict[str, dict[str, Any]]:
    schemas = _ORIGINAL_INPUT_SCHEMAS()
    for name, task in FIXED_TASK_TOOLS.items():
        schemas[name] = _task_input_schema(task)
    schemas[LIST_PACKAGE_SCRIPTS_TOOL] = _list_package_scripts_input_schema()
    schemas[REPLACE_TEXT_TOOL] = _replace_text_input_schema()
    return schemas


def _package_scripts_payload(package_json: str) -> dict[str, Any]:
    try:
        parsed = json.loads(package_json)
    except json.JSONDecodeError as exc:
        raise _server.ToolFailure(
            "INVALID_JSON",
            "package.json is not valid JSON.",
            category="validation",
            details={"line": exc.lineno, "column": exc.colno},
        ) from exc
    if not isinstance(parsed, dict):
        raise _server.ToolFailure("INVALID_PACKAGE_JSON", "package.json must contain a JSON object.", category="validation")
    raw_scripts = parsed.get("scripts", {})
    if raw_scripts is None:
        raw_scripts = {}
    if not isinstance(raw_scripts, dict):
        raise _server.ToolFailure("INVALID_PACKAGE_JSON", "package.json scripts must be an object.", category="validation")
    scripts = {str(name): command for name, command in raw_scripts.items() if isinstance(command, str)}
    return {
        "scripts": dict(sorted(scripts.items())),
        "script_count": len(scripts),
    }


def _replace_text_content(
    content: str,
    *,
    old: str,
    new: str,
    expected_replacements: int,
) -> tuple[str, int]:
    if not old:
        raise _server.ToolFailure("INVALID_ARGUMENT", "old must be a non-empty string.", category="validation")
    if expected_replacements < 1:
        raise _server.ToolFailure(
            "INVALID_ARGUMENT",
            "expected_replacements must be >= 1.",
            category="validation",
        )
    replacements = content.count(old)
    if replacements != expected_replacements:
        raise _server.ToolFailure(
            "REPLACE_TEXT_MISMATCH",
            f"Expected {expected_replacements} replacements, found {replacements}.",
            category="validation",
            details={"expected_replacements": expected_replacements, "actual_replacements": replacements},
        )
    return content.replace(old, new), replacements


def _run_fixed_task(runtime: _server.Runtime, args: dict[str, Any], task_name: str) -> dict[str, Any]:
    task = FIXED_TASK_TOOLS[task_name]
    exec_args = {
        "cmd": task.cmd,
        "workdir": str(args.get("workdir", ".") or "."),
        "timeout_ms": _bounded_int(
            args.get("timeout_ms"),
            default=task.timeout_ms,
            minimum=1,
            maximum=task.max_timeout_ms,
        ),
        "yield_time_ms": _bounded_int(args.get("yield_time_ms"), default=1000, minimum=0, maximum=30000),
        "max_output_bytes": _bounded_int(
            args.get("max_output_bytes"),
            default=65536,
            minimum=1,
            maximum=1048576,
        ),
        "stdin": "",
        "tty": False,
        "env": {},
    }
    payload = runtime.exec_command(exec_args)
    payload["task"] = task_name
    payload["fixed_command"] = task.cmd
    payload.setdefault("warnings", [])
    return payload


def _list_package_scripts(runtime: _server.Runtime, args: dict[str, Any]) -> dict[str, Any]:
    raw_path = str(args.get("path", "package.json") or "package.json")
    resolved = runtime.resolve_existing(raw_path)
    if resolved.path.is_dir():
        raise _server.ToolFailure("IS_DIRECTORY", "Path is a directory.", category="validation")
    package_json = _server.read_text_preserve_newlines(resolved.path)
    return {"path": resolved.display, **_package_scripts_payload(package_json)}


def _replace_text(runtime: _server.Runtime, args: dict[str, Any]) -> dict[str, Any]:
    raw_path = str(args.get("path", ""))
    old = str(args.get("old", ""))
    new = str(args.get("new", ""))
    expected_replacements = _bounded_int(
        args.get("expected_replacements"),
        default=1,
        minimum=1,
        maximum=1_000_000,
    )
    dry_run = bool(args.get("dry_run", False))

    runtime.workspace.reject_write_symlink(raw_path)
    resolved = runtime.resolve_existing(raw_path)
    if resolved.path.is_dir():
        raise _server.ToolFailure("IS_DIRECTORY", "Path is a directory.", category="validation")
    content = _server.read_text_preserve_newlines(resolved.path)
    updated, replacements = _replace_text_content(
        content,
        old=old,
        new=new,
        expected_replacements=expected_replacements,
    )
    if not dry_run:
        runtime._commit_staged_files({resolved.display: updated})
    return {
        "path": resolved.display,
        "dry_run": dry_run,
        "changed": updated != content,
        "replacements": replacements,
        "warnings": [],
    }


def _make_task_handler(task_name: str) -> Callable[[_server.Runtime, dict[str, Any]], dict[str, Any]]:
    def _handler(runtime: _server.Runtime, args: dict[str, Any]) -> dict[str, Any]:
        return _run_fixed_task(runtime, args, task_name)

    _handler.__name__ = task_name
    return _handler


def install_chatgpt_task_tools() -> None:
    global _PATCHED
    if _PATCHED:
        return

    _server.input_schemas = _input_schemas_with_chatgpt_tools
    for name, task in FIXED_TASK_TOOLS.items():
        _server.TOOL_REGISTRY[name] = _server.ToolSpec(
            title=task.title,
            description=task.description,
            read_only=False,
            destructive=False,
            idempotent=False,
            open_world=False,
        )
        setattr(_server.Runtime, name, _make_task_handler(name))

    _server.TOOL_REGISTRY[LIST_PACKAGE_SCRIPTS_TOOL] = _server.ToolSpec(
        title="List package scripts",
        description="Read package.json scripts from the workspace without exposing an arbitrary shell command argument.",
        read_only=True,
        idempotent=True,
        in_read_only_profile=True,
    )
    setattr(_server.Runtime, LIST_PACKAGE_SCRIPTS_TOOL, _list_package_scripts)

    _server.TOOL_REGISTRY[REPLACE_TEXT_TOOL] = _server.ToolSpec(
        title="Replace text",
        description="Replace an exact text occurrence count in one workspace UTF-8 file.",
        destructive=True,
        idempotent=False,
        open_world=False,
    )
    setattr(_server.Runtime, REPLACE_TEXT_TOOL, _replace_text)

    _server.FULL_TOOL_NAMES = tuple(_server.TOOL_REGISTRY)
    _server.READ_ONLY_TOOL_NAMES = tuple(
        name for name, spec in _server.TOOL_REGISTRY.items() if spec.in_read_only_profile
    )
    _PATCHED = True


def main() -> int:
    install_chatgpt_task_tools()
    return _server.main()


if __name__ == "__main__":
    raise SystemExit(main())
