#!/bin/bash
# PreToolUse hook: block destructive find and sqlite3 commands

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | jq -r '.tool_input.command // empty')

[ -z "$COMMAND" ] && exit 0

# --- find: block -exec, -execdir, -delete, -ok ---
if echo "$COMMAND" | grep -qE '(^|[|;&]\s*)find\b'; then
  if echo "$COMMAND" | grep -qE -- '-(exec|execdir|delete|ok)\b'; then
    echo "Blocked: find with destructive flags (-exec, -execdir, -delete, -ok)" >&2
    exit 2
  fi
fi

# --- sqlite3: block write/modify statements ---
if echo "$COMMAND" | grep -qE '(^|[|;&]\s*)sqlite3\b'; then
  if echo "$COMMAND" | grep -qiE '\b(INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|REPLACE|ATTACH|DETACH|REINDEX|VACUUM|PRAGMA\s+.*=)\b'; then
    echo "Blocked: sqlite3 with write/modify statement (INSERT/UPDATE/DELETE/DROP/ALTER/CREATE/REPLACE)" >&2
    exit 2
  fi
fi

exit 0
