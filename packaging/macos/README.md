# macOS Desktop Packaging Assets

Put optional desktop packaging assets here.

## App Icon

- Default source icon (auto-converted during build): `logo/Meta Screener LOGO图标 透明背景.svg`
- Optional prebuilt icon file: `MetaScreener.icns`
- Used by: `packaging/pyinstaller/metascreener-desktop.spec`
- Override from CLI:
  - `uv run python scripts/build_desktop.py --icon /path/to/MetaScreener.icns`
  - `uv run python scripts/build_desktop.py --icon /path/to/logo.svg`

## Build Commands

- `.app` / onedir bundle:
  - `make build-desktop`
- `.dmg` (macOS only):
  - `make build-desktop-dmg`

## Signing (codesign)

### Required

- macOS
- Apple Developer ID Application certificate installed in Keychain

### Environment variable (recommended)

- `METASCREENER_CODESIGN_IDENTITY`
  - Example: `Developer ID Application: Your Name (TEAMID)`

### Commands

- Sign both `.app` and `.dmg` (if present in `dist/desktop/`):
  - `make sign-desktop-macos`
- Custom identity / artifact paths:
  - `uv run python scripts/sign_macos_desktop.py --identity "Developer ID Application: ..."`

Default entitlements file:

- `packaging/macos/entitlements.plist`

## Notarization (notarytool)

### Authentication (choose one)

1. Keychain profile (recommended)
- Env: `METASCREENER_NOTARY_KEYCHAIN_PROFILE`
- Example setup:
  - `xcrun notarytool store-credentials metascreener-notary --apple-id ... --team-id ... --password ...`

2. Direct credentials via env vars
- `METASCREENER_NOTARY_APPLE_ID`
- `METASCREENER_NOTARY_TEAM_ID`
- `METASCREENER_NOTARY_PASSWORD`

### Commands

- Notarize default desktop DMG and staple tickets:
  - `make notarize-desktop-macos`
- One-shot release flow:
  - `make release-desktop-macos`

Notes:

- `release-desktop-macos` expects signing identity and notarization credentials to already be configured.
- The notarization script staples the submitted artifact and also staples `MetaScreener.app` when notarizing a DMG.
