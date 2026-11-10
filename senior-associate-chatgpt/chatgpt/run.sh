#!/bin/sh
# stdout is reserved for MCP. No API key or background model process is started.
set -eu
here="$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
for sa_uv in "$(command -v uv 2>/dev/null || true)" /opt/homebrew/bin/uv /usr/local/bin/uv "$HOME/.local/bin/uv" "$HOME/.cargo/bin/uv"; do
  if [ -n "$sa_uv" ] && [ -x "$sa_uv" ]; then
    exec "$sa_uv" run --quiet --locked --script "$here/server.py" "$@"
  fi
done
printf '%s\n' 'Senior Associate needs uv. Ask ChatGPT to install uv for Senior Associate, then reopen the plugin.' >&2
exit 127
