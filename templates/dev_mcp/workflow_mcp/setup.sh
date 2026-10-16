#!/bin/sh
set -eu

cd /workspace/dev_mcp/workflow_mcp
uv python install --no-bin
uv sync --locked
exec uv run --no-sync python server.py
