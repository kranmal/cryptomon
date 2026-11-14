#!/usr/bin/env bash
# Install cryptomon for current user (pipx preferred, venv fallback). Adds app menu entry.
set -euo pipefail
cd "$(dirname "$0")"
if command -v pipx >/dev/null; then
  pipx install --force .
else
  python3 -m venv "$HOME/.local/share/cryptomon-venv"
  "$HOME/.local/share/cryptomon-venv/bin/pip" install .
  mkdir -p "$HOME/.local/bin"
  ln -sf "$HOME/.local/share/cryptomon-venv/bin/cryptomon" "$HOME/.local/bin/cryptomon"
fi
mkdir -p "$HOME/.local/share/applications"
cp data/cryptomon.desktop "$HOME/.local/share/applications/"
mkdir -p "$HOME/.local/share/icons/hicolor/scalable/apps"
cp src/cryptomon/icon.svg "$HOME/.local/share/icons/hicolor/scalable/apps/cryptomon.svg"
gtk-update-icon-cache -f -t "$HOME/.local/share/icons/hicolor" >/dev/null 2>&1 || true
echo "Installed. Run: cryptomon   (ensure ~/.local/bin is in PATH)"
