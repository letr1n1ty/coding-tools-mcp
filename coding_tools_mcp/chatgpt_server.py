from __future__ import annotations

import os
import shlex
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from . import server as _server


@dataclass(frozen=True)
class FixedTaskTool:
    title: str
    description: str
    cmd: str
    timeout_ms: int
    max_timeout_ms: int


@dataclass(frozen=True)
class XcodeTool:
    title: str
    description: str
    read_only: bool


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
    "run_addon_validation": FixedTaskTool(
        title="Run addon validation",
        description=(
            "Run `npm run validate:addon --if-present` in the workspace without exposing an arbitrary shell command argument."
        ),
        cmd="npm run validate:addon --if-present",
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


XCODE_TOOLS: dict[str, XcodeTool] = {
    "list_xcode_projects": XcodeTool(
        title="List Xcode projects",
        description="List Xcode projects, workspaces, and Swift packages inside the configured workspace.",
        read_only=True,
    ),
    "list_xcode_schemes": XcodeTool(
        title="List Xcode schemes",
        description="Run `xcodebuild -list -json` for one workspace or project.",
        read_only=True,
    ),
    "show_xcode_destinations": XcodeTool(
        title="Show Xcode destinations",
        description="Run `xcodebuild -showdestinations` for one workspace or project scheme.",
        read_only=True,
    ),
    "run_xcode_build_simulator": XcodeTool(
        title="Run Xcode simulator build",
        description="Run an Xcode build for an iOS Simulator destination without exposing an arbitrary shell command.",
        read_only=False,
    ),
    "run_xcode_test_simulator": XcodeTool(
        title="Run Xcode simulator tests",
        description="Run Xcode tests for an iOS Simulator destination without exposing an arbitrary shell command.",
        read_only=False,
    ),
    "run_swift_tests": XcodeTool(
        title="Run Swift tests",
        description="Run `swift test` in the workspace without exposing an arbitrary shell command.",
        read_only=False,
    ),
}


_ORIGINAL_INPUT_SCHEMAS: Callable[[], dict[str, dict[str, Any]]] = _server.input_schemas
_PATCHED = False


def _bounded_int(value: Any, *, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return max(minimum, min(parsed, maximum))


def _safe_relative_path(value: Any, *, field: str, default: str = "") -> str:
    text = str(value or default).strip()
    if not text:
        return ""
    normalized = text.replace("\\", "/")
    if (
        normalized.startswith("/")
        or normalized.startswith("~")
        or "://" in normalized
        or any(part == ".." for part in PurePosixPath(normalized).parts)
    ):
        raise _server.ToolFailure(
            "INVALID_ARGUMENT",
            f"{field} must be a workspace-relative path.",
            category="validation",
            details={"field": field, "value": text[:200]},
        )
    return normalized


def _safe_path_with_suffix(value: Any, *, field: str, suffix: str) -> str:
    path = _safe_relative_path(value, field=field)
    if not path:
        return ""
    if not path.endswith(suffix):
        raise _server.ToolFailure(
            "INVALID_ARGUMENT",
            f"{field} must end with {suffix}.",
            category="validation",
            details={"field": field, "value": path[:200], "suffix": suffix},
        )
    return path


def _safe_text_value(value: Any, *, field: str, required: bool = False, default: str = "") -> str:
    text = str(value or default).strip()
    if required and not text:
        raise _server.ToolFailure(
            "INVALID_ARGUMENT",
            f"{field} is required.",
            category="validation",
            details={"field": field},
        )
    if any(ch in text for ch in "\r\n\x00"):
        raise _server.ToolFailure(
            "INVALID_ARGUMENT",
            f"{field} must not contain control characters.",
            category="validation",
            details={"field": field},
        )
    if len(text) > 512:
        raise _server.ToolFailure(
            "INVALID_ARGUMENT",
            f"{field} is too long.",
            category="validation",
            details={"field": field, "max_length": 512},
        )
    return text


def _quote_cmd(parts: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in parts if part != "")


def _task_control_schema(*, default_timeout: int, max_timeout: int, include_workdir: bool = True) -> dict[str, Any]:
    properties: dict[str, Any] = {
        "timeout_ms": {
            "type": "integer",
            "minimum": 1,
            "maximum": max_timeout,
            "default": default_timeout,
        },
        "yield_time_ms": {"type": "integer", "minimum": 0, "maximum": 30000, "default": 1000},
        "max_output_bytes": {"type": "integer", "minimum": 1, "maximum": 1048576, "default": 65536},
    }
    if include_workdir:
        properties = {"workdir": {"type": "string", "default": "."}, **properties}
    return properties


def _task_input_schema(task: FixedTaskTool) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": _task_control_schema(default_timeout=task.timeout_ms, max_timeout=task.max_timeout_ms),
        "additionalProperties": False,
    }


def _xcode_selector_schema_properties() -> dict[str, Any]:
    return {
        "workspace": {"type": "string", "description": "Workspace-relative .xcworkspace path."},
        "project": {"type": "string", "description": "Workspace-relative .xcodeproj path."},
    }


def _xcode_input_schema(name: str) -> dict[str, Any]:
    if name == "list_xcode_projects":
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "default": "."},
                "max_depth": {"type": "integer", "minimum": 1, "maximum": 20, "default": 6},
                "max_results": {"type": "integer", "minimum": 1, "maximum": 500, "default": 100},
            },
            "additionalProperties": False,
        }
    if name == "list_xcode_schemes":
        return {
            "type": "object",
            "properties": {
                **_xcode_selector_schema_properties(),
                **_task_control_schema(default_timeout=60_000, max_timeout=180_000),
            },
            "additionalProperties": False,
        }
    if name == "show_xcode_destinations":
        return {
            "type": "object",
            "properties": {
                **_xcode_selector_schema_properties(),
                "scheme": {"type": "string", "minLength": 1},
                **_task_control_schema(default_timeout=60_000, max_timeout=180_000),
            },
            "required": ["scheme"],
            "additionalProperties": False,
        }
    if name in {"run_xcode_build_simulator", "run_xcode_test_simulator"}:
        return {
            "type": "object",
            "properties": {
                **_xcode_selector_schema_properties(),
                "scheme": {"type": "string", "minLength": 1},
                "destination": {
                    "type": "string",
                    "minLength": 1,
                    "description": "xcodebuild destination that must target platform=iOS Simulator.",
                },
                "configuration": {"type": "string", "default": "Debug"},
                "disable_code_signing": {"type": "boolean", "default": True},
                **_task_control_schema(default_timeout=300_000, max_timeout=900_000),
            },
            "required": ["scheme", "destination"],
            "additionalProperties": False,
        }
    if name == "run_swift_tests":
        return {
            "type": "object",
            "properties": _task_control_schema(default_timeout=180_000, max_timeout=600_000),
            "additionalProperties": False,
        }
    raise KeyError(name)


def _input_schemas_with_fixed_tasks() -> dict[str, dict[str, Any]]:
    schemas = _ORIGINAL_INPUT_SCHEMAS()
    for name, task in FIXED_TASK_TOOLS.items():
        schemas[name] = _task_input_schema(task)
    for name in XCODE_TOOLS:
        schemas[name] = _xcode_input_schema(name)
    return schemas


def _exec_controls(args: dict[str, Any], *, default_timeout: int, max_timeout: int) -> dict[str, Any]:
    return {
        "timeout_ms": _bounded_int(
            args.get("timeout_ms"),
            default=default_timeout,
            minimum=1,
            maximum=max_timeout,
        ),
        "yield_time_ms": _bounded_int(args.get("yield_time_ms"), default=1000, minimum=0, maximum=30000),
        "max_output_bytes": _bounded_int(
            args.get("max_output_bytes"),
            default=65536,
            minimum=1,
            maximum=1048576,
        ),
    }


def _run_command(
    runtime: _server.Runtime,
    args: dict[str, Any],
    *,
    cmd: str,
    default_timeout: int,
    max_timeout: int,
    task_name: str,
) -> dict[str, Any]:
    exec_args = {
        "cmd": cmd,
        "workdir": _safe_relative_path(args.get("workdir"), field="workdir", default="."),
        **_exec_controls(args, default_timeout=default_timeout, max_timeout=max_timeout),
        "stdin": "",
        "tty": False,
        "env": {},
    }
    payload = runtime.exec_command(exec_args)
    payload["task"] = task_name
    payload["fixed_command"] = cmd
    payload.setdefault("warnings", [])
    return payload


def _run_fixed_task(runtime: _server.Runtime, args: dict[str, Any], task_name: str) -> dict[str, Any]:
    task = FIXED_TASK_TOOLS[task_name]
    return _run_command(
        runtime,
        args,
        cmd=task.cmd,
        default_timeout=task.timeout_ms,
        max_timeout=task.max_timeout_ms,
        task_name=task_name,
    )


def _xcode_selector_parts(args: dict[str, Any]) -> list[str]:
    workspace = _safe_path_with_suffix(args.get("workspace"), field="workspace", suffix=".xcworkspace")
    project = _safe_path_with_suffix(args.get("project"), field="project", suffix=".xcodeproj")
    if bool(workspace) == bool(project):
        raise _server.ToolFailure(
            "INVALID_ARGUMENT",
            "Provide exactly one of workspace or project.",
            category="validation",
            details={"fields": ["workspace", "project"]},
        )
    return ["-workspace", workspace] if workspace else ["-project", project]


def _require_ios_simulator_destination(destination: str) -> None:
    if "platform=iOS Simulator" not in destination:
        raise _server.ToolFailure(
            "INVALID_ARGUMENT",
            "destination must target platform=iOS Simulator.",
            category="validation",
            details={"destination": destination[:200]},
        )


def _list_xcode_projects(runtime: _server.Runtime, args: dict[str, Any]) -> dict[str, Any]:
    path = _safe_relative_path(args.get("path"), field="path", default=".")
    resolved = runtime.resolve_existing(path)
    if not resolved.path.is_dir():
        raise _server.ToolFailure("NOT_A_DIRECTORY", "path is not a directory.", category="validation")

    root = runtime.workspace.root
    max_depth = _bounded_int(args.get("max_depth"), default=6, minimum=1, maximum=20)
    max_results = _bounded_int(args.get("max_results"), default=100, minimum=1, maximum=500)
    projects: list[str] = []
    workspaces: list[str] = []
    swift_packages: list[str] = []
    truncated = False

    base_depth = len(resolved.path.relative_to(root).parts) if resolved.path != root else 0
    for current, dirs, files in os.walk(resolved.path):
        current_path = Path(current)
        rel_depth = len(current_path.relative_to(root).parts) - base_depth
        dirs[:] = [item for item in dirs if item not in _server.DEFAULT_EXCLUDED_NAMES]
        if rel_depth >= max_depth:
            dirs[:] = []

        for dirname in list(dirs):
            if dirname.endswith(".xcodeproj"):
                projects.append((current_path / dirname).relative_to(root).as_posix())
            elif dirname.endswith(".xcworkspace"):
                workspaces.append((current_path / dirname).relative_to(root).as_posix())

        if "Package.swift" in files:
            swift_packages.append((current_path / "Package.swift").relative_to(root).as_posix())

        if len(projects) + len(workspaces) + len(swift_packages) >= max_results:
            truncated = True
            break

    return {
        "path": path,
        "projects": projects[:max_results],
        "workspaces": workspaces[:max_results],
        "swift_packages": swift_packages[:max_results],
        "count": min(len(projects) + len(workspaces) + len(swift_packages), max_results),
        "truncated": truncated,
    }


def _list_xcode_schemes(runtime: _server.Runtime, args: dict[str, Any]) -> dict[str, Any]:
    parts = ["xcodebuild", *_xcode_selector_parts(args), "-list", "-json"]
    return _run_command(
        runtime,
        args,
        cmd=_quote_cmd(parts),
        default_timeout=60_000,
        max_timeout=180_000,
        task_name="list_xcode_schemes",
    )


def _show_xcode_destinations(runtime: _server.Runtime, args: dict[str, Any]) -> dict[str, Any]:
    scheme = _safe_text_value(args.get("scheme"), field="scheme", required=True)
    parts = ["xcodebuild", *_xcode_selector_parts(args), "-scheme", scheme, "-showdestinations"]
    return _run_command(
        runtime,
        args,
        cmd=_quote_cmd(parts),
        default_timeout=60_000,
        max_timeout=180_000,
        task_name="show_xcode_destinations",
    )


def _run_xcode_action(runtime: _server.Runtime, args: dict[str, Any], *, action: str, task_name: str) -> dict[str, Any]:
    scheme = _safe_text_value(args.get("scheme"), field="scheme", required=True)
    destination = _safe_text_value(args.get("destination"), field="destination", required=True)
    configuration = _safe_text_value(args.get("configuration"), field="configuration", default="Debug")
    _require_ios_simulator_destination(destination)

    parts = [
        "xcodebuild",
        *_xcode_selector_parts(args),
        "-scheme",
        scheme,
        "-configuration",
        configuration,
        "-destination",
        destination,
    ]
    if bool(args.get("disable_code_signing", True)):
        parts.append("CODE_SIGNING_ALLOWED=NO")
    parts.append(action)
    return _run_command(
        runtime,
        args,
        cmd=_quote_cmd(parts),
        default_timeout=300_000,
        max_timeout=900_000,
        task_name=task_name,
    )


def _run_xcode_build_simulator(runtime: _server.Runtime, args: dict[str, Any]) -> dict[str, Any]:
    return _run_xcode_action(runtime, args, action="build", task_name="run_xcode_build_simulator")


def _run_xcode_test_simulator(runtime: _server.Runtime, args: dict[str, Any]) -> dict[str, Any]:
    return _run_xcode_action(runtime, args, action="test", task_name="run_xcode_test_simulator")


def _run_swift_tests(runtime: _server.Runtime, args: dict[str, Any]) -> dict[str, Any]:
    return _run_command(
        runtime,
        args,
        cmd="swift test",
        default_timeout=180_000,
        max_timeout=600_000,
        task_name="run_swift_tests",
    )


def _make_task_handler(task_name: str) -> Callable[[_server.Runtime, dict[str, Any]], dict[str, Any]]:
    def _handler(runtime: _server.Runtime, args: dict[str, Any]) -> dict[str, Any]:
        return _run_fixed_task(runtime, args, task_name)

    _handler.__name__ = task_name
    return _handler


def install_chatgpt_task_tools() -> None:
    global _PATCHED
    if _PATCHED:
        return

    _server.input_schemas = _input_schemas_with_fixed_tasks
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

    xcode_handlers = {
        "list_xcode_projects": _list_xcode_projects,
        "list_xcode_schemes": _list_xcode_schemes,
        "show_xcode_destinations": _show_xcode_destinations,
        "run_xcode_build_simulator": _run_xcode_build_simulator,
        "run_xcode_test_simulator": _run_xcode_test_simulator,
        "run_swift_tests": _run_swift_tests,
    }
    for name, tool in XCODE_TOOLS.items():
        _server.TOOL_REGISTRY[name] = _server.ToolSpec(
            title=tool.title,
            description=tool.description,
            read_only=tool.read_only,
            destructive=False,
            idempotent=False,
            open_world=False,
        )
        setattr(_server.Runtime, name, xcode_handlers[name])

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
