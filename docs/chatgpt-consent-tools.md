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

General task tools:

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

Xcode and iOS Simulator tools:

- `list_xcode_projects`: lists `.xcodeproj`, `.xcworkspace`, and `Package.swift` files inside the configured workspace.
- `list_xcode_schemes`: runs `xcodebuild -list -json` for one workspace or project.
- `show_xcode_destinations`: runs `xcodebuild -showdestinations` for one workspace or project scheme.
- `run_xcode_build_simulator`: runs `xcodebuild build` for an iOS Simulator destination.
- `run_xcode_test_simulator`: runs `xcodebuild test` for an iOS Simulator destination.
- `run_swift_tests`: runs `swift test`.

## Common execution controls

Most runner tools accept only bounded execution controls:

- `workdir`
- `timeout_ms`
- `yield_time_ms`
- `max_output_bytes`

They do not accept arbitrary `cmd`, `env`, `stdin`, or `tty` arguments.

## Xcode workflow

A typical iOS Simulator workflow is:

1. Call `list_xcode_projects` to find `.xcworkspace`, `.xcodeproj`, or Swift package roots.
2. Call `list_xcode_schemes` with exactly one of `workspace` or `project`.
3. Call `show_xcode_destinations` with the same selector and a shared scheme.
4. Call `run_xcode_build_simulator` or `run_xcode_test_simulator` with a destination containing `platform=iOS Simulator`.

Example arguments:

```json
{
  "workspace": "App.xcworkspace",
  "scheme": "App",
  "destination": "platform=iOS Simulator,name=iPhone 16",
  "configuration": "Debug"
}
```

The simulator build/test tools require the destination to target `platform=iOS Simulator`. They do not handle Apple ID login, signing certificate management, provisioning profiles, physical devices, TestFlight upload, or App Store Connect operations.

`disable_code_signing` defaults to `true` for simulator build/test calls and adds `CODE_SIGNING_ALLOWED=NO` to the `xcodebuild` invocation. Set it to `false` only when the project requires signing behavior during simulator builds.

## Annotation intent

The general fixed task tools are registered with:

```json
{
  "readOnlyHint": false,
  "destructiveHint": false,
  "idempotentHint": false,
  "openWorldHint": false
}
```

The Xcode inspection tools are marked read-only. The Xcode build/test tools execute local workspace code and write build/test artifacts, so they are not read-only. They are marked non-destructive because they do not intentionally delete, overwrite, publish, or send data outside the workspace. They are marked closed-world because their command templates do not intentionally perform network or external-recipient operations.

This can reduce host-side ambiguity for common tasks such as Vitest, typecheck, build, addon validation, Xcode scheme discovery, and iOS Simulator build/test. It cannot force a ChatGPT host to skip user confirmation; the host still decides whether a confirmation prompt is required.

## Why keep `exec_command`?

`exec_command` remains available for advanced coding work and unusual toolchains. The fixed task tools cover common validation paths where a narrower schema is more accurate than exposing a free-form shell command.
