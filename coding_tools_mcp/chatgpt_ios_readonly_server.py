from __future__ import annotations

import os

from . import server as _server
from .chatgpt_ios_server import main as _chatgpt_ios_main


DEFAULT_TOOL_PROFILE = "compat-readonly-all"


def main() -> int:
    os.environ.setdefault(f"{_server.ENV_PREFIX}_TOOL_PROFILE", DEFAULT_TOOL_PROFILE)
    return _chatgpt_ios_main()


if __name__ == "__main__":
    raise SystemExit(main())
