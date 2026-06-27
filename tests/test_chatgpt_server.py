from __future__ import annotations

import unittest

from coding_tools_mcp import chatgpt_server


class ChatGPTServerHelperTests(unittest.TestCase):
    def test_package_scripts_payload_filters_string_scripts(self) -> None:
        payload = chatgpt_server._package_scripts_payload(
            '{"scripts":{"test":"vitest run","typecheck":"tsc --noEmit","bad":123}}'
        )

        self.assertEqual(
            payload,
            {
                "scripts": {
                    "test": "vitest run",
                    "typecheck": "tsc --noEmit",
                },
                "script_count": 2,
            },
        )

    def test_replace_text_content_requires_expected_count(self) -> None:
        with self.assertRaises(chatgpt_server._server.ToolFailure) as context:
            chatgpt_server._replace_text_content(
                "alpha beta alpha",
                old="alpha",
                new="gamma",
                expected_replacements=1,
            )

        self.assertEqual(context.exception.code, "REPLACE_TEXT_MISMATCH")
        self.assertEqual(context.exception.details["actual_replacements"], 2)

    def test_replace_text_content_replaces_exact_count(self) -> None:
        updated, replacements = chatgpt_server._replace_text_content(
            "alpha beta",
            old="alpha",
            new="gamma",
            expected_replacements=1,
        )

        self.assertEqual(updated, "gamma beta")
        self.assertEqual(replacements, 1)

    def test_install_chatgpt_task_tools_registers_workflow_helpers(self) -> None:
        chatgpt_server.install_chatgpt_task_tools()

        schemas = chatgpt_server._server.input_schemas()
        self.assertIn("run_npm_validate", schemas)
        self.assertIn("run_npm_build_renderer", schemas)
        self.assertIn("run_npm_validate_addons", schemas)
        self.assertIn("list_package_scripts", schemas)
        self.assertIn("replace_text", schemas)

        self.assertIn("list_package_scripts", chatgpt_server._server.READ_ONLY_TOOL_NAMES)
        self.assertIn("replace_text", chatgpt_server._server.FULL_TOOL_NAMES)


if __name__ == "__main__":
    unittest.main()
