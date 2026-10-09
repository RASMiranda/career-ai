#!/usr/bin/env bash
# Runs on YOUR machine (macOS/Linux). Same as local-apply.ps1.
# Usage: scripts/local-apply.sh [--mode assisted|auto] [--dry-run]
set -euo pipefail
export CAREER_DATA="${CAREER_DATA:-$HOME/career-data}"
export PYTHONPATH="$(dirname "$0")/../src"
git -C "$CAREER_DATA" pull --ff-only
# A failed run must not stop the push: what it recorded (failures included) is what the next
# scan emails to you as "apply by hand".
python -m jobscan.apply run "$@" || echo "apply run exited with status $?; pushing what it recorded" >&2
python -m jobscan.apply summary >/dev/null
git -C "$CAREER_DATA" add applications logs reports
if [ -n "$(git -C "$CAREER_DATA" status --porcelain)" ]; then
  git -C "$CAREER_DATA" commit -m "apply run $(date -u +%FT%T)"
  git -C "$CAREER_DATA" push
fi
