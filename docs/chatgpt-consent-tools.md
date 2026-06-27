# ChatGPT consent-friendly task tools

`coding-tools-mcp-chatgpt` starts the normal Coding Tools MCP server and adds fixed-purpose task runner tools for MCP hosts that show stricter confirmation prompts for arbitrary command execution.

These tools do not replace `exec_command`. They wrap common local development commands in narrower tool schemas so the host can display a clearer action than a free-form shell command.

## Start command

```bash
coding-tools-mcp-chatgpt --stdio --workspace /path/to/repo
```

With `uvx`:

```bash
uvx coding-tools-mcp --from /path/to/checkout coding-tools-mcp-chatgpt --stdio --workspace /path/to/repo
```

## Added tools

- `run_vitest`: runs `npx --no-install vitest run`.
- `run_npm_test`: runs `npm test`.
- `run_npm_typecheck`: runs `npm run typecheck --if-present`.
- `run_npm_lint`: runs `npm run lint --if-present`.
- `run_npm_build`: runs `npm run build --if-present`.
- `run_addon_validation`: runs `npm run validate:addon --if-present`.
- `run_python_tests`: runs `python -m unittest discover -s tests -p 'test_*.py'`.
- `run_make_test`: runs `make test`.
- `run_make_ci`: runs `make ci`.
- `run_make_compliance`: runs `make compliance`.

Each tool accepts only bounded execution controls:

- `workdir`
- `timeout_ms`
- `yield_time_ms`
- `max_output_bytes`

They do not accept arbitrary `cmd`, `env`, `stdin`, or `tty` arguments.

## Annotation intent

The fixed task tools are registered with:

```json
{
  "readOnlyHint": false,
  "destructiveHint": false,
  "idempotentHint": false,
  "openWorldHint": false
}
```

They execute local workspace code, so they are not read-only. They are marked non-destructive because they do not intentionally delete, overwrite, publish, or send data outside the workspace. They are marked closed-world because their command templates do not intentionally perform network or external-recipient operations.

This can reduce host-side ambiguity for common tasks such as Vitest, typecheck, build, and addon validation. It cannot force a ChatGPT host to skip user confirmation; the host still decides whether a confirmation prompt is required.

## Why keep `exec_command`?

`exec_command` remains available for advanced coding work and unusual toolchains. The fixed task tools cover common validation paths where a narrower schema is more accurate than exposing a free-form shell command.
