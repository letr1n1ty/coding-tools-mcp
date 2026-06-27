# ChatGPT iOS/Xcode task tools

`coding-tools-mcp-chatgpt-ios` is an opt-in entrypoint for iOS and Swift development workflows in ChatGPT.
It keeps the general ChatGPT fixed task tools and adds Xcode/iOS Simulator tools only when this entrypoint is used.

## Start command

```bash
coding-tools-mcp-chatgpt-ios --stdio --workspace /path/to/ios/repo
```

## Added Xcode tools

- `list_xcode_projects`: lists `.xcodeproj`, `.xcworkspace`, and `Package.swift` files inside the configured workspace.
- `list_xcode_schemes`: runs `xcodebuild -list -json` for one workspace or project.
- `show_xcode_destinations`: runs `xcodebuild -showdestinations` for one workspace or project scheme.
- `run_xcode_build_simulator`: runs `xcodebuild build` for an iOS Simulator destination.
- `run_xcode_test_simulator`: runs `xcodebuild test` for an iOS Simulator destination.
- `run_swift_tests`: runs `swift test`.

## Workflow

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

## Scope limits

The simulator build/test tools require the destination to target `platform=iOS Simulator`.
They do not handle Apple ID login, signing certificate management, provisioning profiles, physical devices, TestFlight upload, or App Store Connect operations.

`disable_code_signing` defaults to `true` for simulator build/test calls and adds `CODE_SIGNING_ALLOWED=NO` to the `xcodebuild` invocation. Set it to `false` only when the project requires signing behavior during simulator builds.

The general `coding-tools-mcp-chatgpt` entrypoint intentionally does not load these Xcode tools, so non-iOS projects do not see unrelated Xcode actions by default.
