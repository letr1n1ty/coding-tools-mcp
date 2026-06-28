from __future__ import annotations

import os

from . import server as _server
from .chatgpt_server import main as _chatgpt_main


DEFAULT_TOOL_PROFILE = "compat-readonly-all"


def main() -> int:
    """Run the ChatGPT entrypoint with write-capable tools advertised as read-only by default."""
    os.environ.setdefault(f"{_server.ENV_PREFIX}_TOOL_PROFILE", DEFAULT_TOOL_PROFILE)
    return _chatgpt_main()


if __name__ == "__main__":
    raise SystemExit(main())
