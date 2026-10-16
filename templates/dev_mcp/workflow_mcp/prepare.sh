#!/bin/sh
set -eu

script_dir=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
project_dir=$(CDPATH= cd -- "$script_dir/../.." && pwd)

mkdir -p "$project_dir/feedbacks" "$project_dir/rejected_feedbacks" \
    "$project_dir/_cache/workflow_mcp_uv_cache" \
    "$project_dir/_cache/workflow_mcp_uv_venv" \
    "$project_dir/_cache/workflow_mcp_uv_python"
