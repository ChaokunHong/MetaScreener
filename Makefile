# MetaScreener 2.0 — Build Commands
.PHONY: build-frontend build-backend build build-desktop build-desktop-dmg sign-desktop-macos notarize-desktop-macos release-desktop-macos dev-frontend dev-backend dev clean test lint

# Build React frontend to src/metascreener/web/dist/
build-frontend:
	cd frontend && npm ci && npm run build

# Build Python wheel (includes frontend assets via force-include)
build-backend: build-frontend
	uv build

# Full build: frontend + Python wheel
build: build-backend

# Build packaged desktop shell (PyInstaller onedir bundle)
build-desktop: build-frontend
	uv run python scripts/build_desktop.py --clean

# Build packaged desktop shell + macOS DMG (macOS only)
build-desktop-dmg: build-frontend
	uv run python scripts/build_desktop.py --clean --dmg

# Sign macOS desktop artifacts (.app/.dmg) using codesign
sign-desktop-macos:
	uv run python scripts/sign_macos_desktop.py

# Notarize macOS desktop DMG (staples DMG and .app by default)
notarize-desktop-macos:
	uv run python scripts/notarize_macos_desktop.py

# One-shot macOS desktop release flow: build -> sign -> notarize
release-desktop-macos: build-desktop-dmg sign-desktop-macos notarize-desktop-macos

# Development: run frontend dev server (Vite with HMR)
dev-frontend:
	cd frontend && npm run dev

# Development: run backend API server only
dev-backend:
	uv run metascreener serve --api-only

# Development: run both (use in separate terminals)
dev:
	@echo "Run in two terminals:"
	@echo "  make dev-backend"
	@echo "  make dev-frontend"

# Run all tests
test:
	uv run pytest --tb=short -q

# Lint and type check
lint:
	uv run ruff check src/ tests/
	uv run mypy src/

# Clean build artifacts
clean:
	rm -rf dist/ src/metascreener/web/dist/ frontend/dist/
