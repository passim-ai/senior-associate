#!/bin/sh
# Claude's command-line tool, for plugin commands (install, update, settings). The Claude desktop app carries its own
# copy, so the attorney never installs one; a separately installed `claude` is the fallback.
app_cli=$(ls -d "$HOME/Library/Application Support/Claude/claude-code"/*/*/claude.app/Contents/MacOS/claude 2>/dev/null | sort -V | tail -n 1)
if [ -n "$app_cli" ] && [ -x "$app_cli" ]; then
  exec "$app_cli" "$@"
fi
for c in "$(command -v claude 2>/dev/null)" "$HOME/.local/bin/claude" /opt/homebrew/bin/claude /usr/local/bin/claude; do
  if [ -n "$c" ] && [ -x "$c" ]; then
    exec "$c" "$@"
  fi
done
echo "Claude's command-line tool wasn't found. Update the Claude app (Claude › Check for Updates), then try again." >&2
exit 127
