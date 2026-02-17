#!/usr/bin/env bash
# VIKI CLI one-line install (Unix)
# Usage: curl -fsSL https://raw.githubusercontent.com/toozuuu/viki/main/install.sh | bash
# Or from repo: ./install.sh

set -e
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
cd "$REPO_ROOT"
echo "Installing VIKI from $REPO_ROOT ..."
pip install -e .
echo "Done. Run 'viki' from any directory (e.g. viki . or viki /path/to/project)."
