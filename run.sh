#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "${BASH_SOURCE[0]}")"

if ! command -v uv >/dev/null 2>&1; then
  echo "Error: uv is required. Install uv first: https://docs.astral.sh/uv/getting-started/installation/" >&2
  exit 1
fi

uv sync --locked
uv run --locked python -m starbinder
