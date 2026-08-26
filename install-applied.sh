#!/usr/bin/env bash
# One-time install: put `applied` on your PATH via ~/bin.
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
mkdir -p "$HOME/bin"
ln -sf "$ROOT/applied" "$HOME/bin/applied"
chmod +x "$ROOT/applied"

# Ensure ~/bin is on PATH in .zshrc (idempotent).
MARKER='# job-tracker: applied command'
if ! grep -qF "$MARKER" "$HOME/.zshrc" 2>/dev/null; then
  {
    echo ""
    echo "$MARKER"
    echo 'export PATH="$HOME/bin:$PATH"'
  } >> "$HOME/.zshrc"
  echo "Added ~/bin to PATH in ~/.zshrc"
else
  echo "~/bin already configured in ~/.zshrc"
fi

echo "Installed. Open a new terminal tab, then run: applied"
