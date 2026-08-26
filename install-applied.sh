#!/usr/bin/env bash
# Install job-tracker locally: pip package + `applied` on PATH + Print PDF service.
set -e
ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT"

# Project-local venv so deps and the console script stay self-contained.
if [ ! -x "$ROOT/.venv/bin/python" ]; then
  python3 -m venv "$ROOT/.venv"
fi

"$ROOT/.venv/bin/pip" install -U pip
"$ROOT/.venv/bin/pip" install -e "$ROOT"

# Replace any previous ~/bin/applied with the pip console script (ln -sf).
mkdir -p "$HOME/bin"
ln -sf "$ROOT/.venv/bin/applied" "$HOME/bin/applied"

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

# Print dialog → PDF menu: "Copy PDF to Clipboard" (no permanent Save as PDF).
PDF_SERVICES="$HOME/Library/PDF Services"
mkdir -p "$PDF_SERVICES"
chmod +x "$ROOT/mac/copy-pdf-to-clipboard"
ln -sf "$ROOT/mac/copy-pdf-to-clipboard" "$PDF_SERVICES/Copy PDF to Clipboard"
echo "Installed Print menu item: PDF → Copy PDF to Clipboard"

echo "Installed. Open a new terminal tab (or source ~/.zshrc), then run: applied"
echo "Re-run this script after pulls to refresh the install."
