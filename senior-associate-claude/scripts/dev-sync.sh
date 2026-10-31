#!/bin/bash
# Development only: mirror the plugin's UI into this session's hot-reloading mods folder
# under a second name (senior-associate-dev, command /matters-dev), so edits load at the
# end of each turn without /reload-plugins. The installed plugin stays untouched.
set -e
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MATTERS="${SENIOR_ASSOCIATE_DEV_MATTERS:-$HOME/Matters}"
EXEMPLARS="${SENIOR_ASSOCIATE_DEV_EXEMPLARS:-$MATTERS/Exemplar}"
DEV="${1:?dev mod folder}"
mkdir -p "$DEV/.claude-plugin" "$DEV/hooks" "$DEV/types" "$DEV/server" "$DEV/tests"
cat > "$DEV/.claude-plugin/plugin.json" <<'JSON'
{
  "name": "senior-associate-dev",
  "version": "0.1.0",
  "description": "Senior Associate UI, development mirror (hot-reloaded)",
  "types": "./types/index.d.ts"
}
JSON
# Every file under hooks/ (the screens included), then the plugin's own names swapped for the dev mirror's.
rsync -a --delete "$SRC/hooks/" "$DEV/hooks/"
sed -i '' \
    -e "s/plugin: 'senior-associate'/plugin: 'senior-associate-dev'/g" \
    -e "s/const PANE = 'senior-associate'/const PANE = 'senior-associate-dev'/" \
    -e "s#config: { matters_root: '', exemplars_dir: '' }#config: { matters_root: '$MATTERS', exemplars_dir: '$EXEMPLARS' }#" \
    "$DEV/hooks/state.ts"
sed -i '' \
    -e "s/name: 'matters'/name: 'matters-dev'/" \
    -e "s/command: 'matters'/command: 'matters-dev'/g" \
    "$DEV/hooks/register.tsx"
sed -e "s/'senior-associate':/'senior-associate-dev':/" "$SRC/types/index.d.ts" > "$DEV/types/index.d.ts"
rsync -a --delete --exclude '__pycache__' "$SRC/server/" "$DEV/server/"
echo "synced to $DEV"
