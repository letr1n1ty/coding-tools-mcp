from __future__ import annotations

import json
import os
import shlex
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any, Callable

from . import server as _server
from .chatgpt_server import install_chatgpt_task_tools


@dataclass(frozen=True)
class XcodeTool:
    title: str
    description: str
    read_only: bool


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

_ORIGINAL_INPUT_SCHEMAS: Callable[[], dict[str, dict[str, Any]]] | None = None
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


def _input_schemas_with_xcode_tools() -> dict[str, dict[str, Any]]:
    assert _ORIGINAL_INPUT_SCHEMAS is not None
    schemas = _ORIGINAL_INPUT_SCHEMAS()
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
        visible_dirs = [item for item in dirs if item not in _server.DEFAULT_EXCLUDED_NAMES]
        for dirname in visible_dirs:
            if dirname.endswith(".xcodeproj"):
                projects.append((current_path / dirname).relative_to(root).as_posix())
            elif dirname.endswith(".xcworkspace"):
                workspaces.append((current_path / dirname).relative_to(root).as_posix())
        dirs[:] = [item for item in visible_dirs if not item.endswith((".xcodeproj", ".xcworkspace"))]
        if rel_depth >= max_depth:
            dirs[:] = []

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
    selector = _xcode_selector_parts(args)
    cmd = _quote_cmd(["xcodebuild", *selector, "-list", "-json"])
    payload = _run_command(
        runtime,
        args,
        cmd=cmd,
        default_timeout=60_000,
        max_timeout=180_000,
        task_name="list_xcode_schemes",
    )
    stdout = str(payload.get("stdout", ""))
    if stdout:
        try:
            payload["parsed"] = json.loads(stdout)
        except json.JSONDecodeError:
            payload.setdefault("warnings", []).append("xcodebuild output was not valid JSON")
    return payload


def _show_xcode_destinations(runtime: _server.Runtime, args: dict[str, Any]) -> dict[str, Any]:
    selector = _xcode_selector_parts(args)
    scheme = _safe_text_value(args.get("scheme"), field="scheme", required=True)
    cmd = _quote_cmd(["xcodebuild", *selector, "-scheme", scheme, "-showdestinations"])
    return _run_command(
        runtime,
        args,
        cmd=cmd,
        default_timeout=60_000,
        max_timeout=180_000,
        task_name="show_xcode_destinations",
    )


def _run_xcode_action(runtime: _server.Runtime, args: dict[str, Any], *, action: str, task_name: str) -> dict[str, Any]:
    selector = _xcode_selector_parts(args)
    scheme = _safe_text_value(args.get("scheme"), field="scheme", required=True)
    destination = _safe_text_value(args.get("destination"), field="destination", required=True)
    _require_ios_simulator_destination(destination)
    configuration = _safe_text_value(args.get("configuration"), field="configuration", default="Debug")
    parts = [
        "xcodebuild",
        *selector,
        "-scheme",
        scheme,
        "-configuration",
        configuration,
        "-destination",
        destination,
        action,
    ]
    if bool(args.get("disable_code_signing", True)):
        parts.append("CODE_SIGNING_ALLOWED=NO")
    return _run_command(
        runtime,
        args,
        cmd=_quote_cmd(parts),
        default_timeout=300_000,
        max_timeout=900_000,
        task_name=task_name,
    )


def _run_swift_tests(runtime: _server.Runtime, args: dict[str, Any]) -> dict[str, Any]:
    return _run_command(
        runtime,
        args,
        cmd="swift test",
        default_timeout=180_000,
        max_timeout=600_000,
        task_name="run_swift_tests",
    )


def _make_xcode_handler(name: str) -> Callable[[_server.Runtime, dict[str, Any]], dict[str, Any]]:
    def _handler(runtime: _server.Runtime, args: dict[str, Any]) -> dict[str, Any]:
        if name == "list_xcode_projects":
            return _list_xcode_projects(runtime, args)
        if name == "list_xcode_schemes":
            return _list_xcode_schemes(runtime, args)
        if name == "show_xcode_destinations":
            return _show_xcode_destinations(runtime, args)
        if name == "run_xcode_build_simulator":
            return _run_xcode_action(runtime, args, action="build", task_name=name)
        if name == "run_xcode_test_simulator":
            return _run_xcode_action(runtime, args, action="test", task_name=name)
        if name == "run_swift_tests":
            return _run_swift_tests(runtime, args)
        raise KeyError(name)

    _handler.__name__ = name
    return _handler


def install_xcode_tools() -> None:
    global _ORIGINAL_INPUT_SCHEMAS, _PATCHED
    if _PATCHED:
        return

    _ORIGINAL_INPUT_SCHEMAS = _server.input_schemas
    _server.input_schemas = _input_schemas_with_xcode_tools
    for name, tool in XCODE_TOOLS.items():
        _server.TOOL_REGISTRY[name] = _server.ToolSpec(
            title=tool.title,
            description=tool.description,
            read_only=tool.read_only,
            destructive=False,
            idempotent=tool.read_only,
            open_world=False,
            in_read_only_profile=tool.read_only,
        )
        setattr(_server.Runtime, name, _make_xcode_handler(name))

    _server.FULL_TOOL_NAMES = tuple(_server.TOOL_REGISTRY)
    _server.READ_ONLY_TOOL_NAMES = tuple(
        name for name, spec in _server.TOOL_REGISTRY.items() if spec.in_read_only_profile
    )
    _PATCHED = True


def main() -> int:
    install_chatgpt_task_tools()
    install_xcode_tools()
    return _server.main()


if __name__ == "__main__":
    raise SystemExit(main())
