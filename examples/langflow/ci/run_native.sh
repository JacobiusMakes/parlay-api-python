#!/usr/bin/env bash
set -euo pipefail

test -n "${NATIVE_ARTIFACTS:-}"
test -n "${LANGFLOW_CONFIG_DIR:-}"
mkdir -p "$NATIVE_ARTIFACTS" "$LANGFLOW_CONFIG_DIR"
chmod 700 "$LANGFLOW_CONFIG_DIR"

# This is an isolated GitHub-hosted process group, never an existing server.
native_pid=""
cleanup() {
  if [[ -n "$native_pid" ]]; then
    kill -TERM -- "-$native_pid" 2>/dev/null || true
    for attempt in 1 2 3 4 5; do
      kill -0 -- "-$native_pid" 2>/dev/null || break
      sleep 1
    done
    kill -KILL -- "-$native_pid" 2>/dev/null || true
    wait "$native_pid" 2>/dev/null || true
  fi
  printf '%s\n' 'Owned Langflow process group stopped.' > "$NATIVE_ARTIFACTS/cleanup.txt"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

setsid python -m langflow run --host 127.0.0.1 --port 7860 --workers 1 \
  > "$NATIVE_ARTIFACTS/langflow.log" 2>&1 &
native_pid=$!
python examples/langflow/ci/validate_native.py \
  --example-dir examples/langflow --artifacts "$NATIVE_ARTIFACTS"
