#!/bin/bash
cd -- "$(dirname -- "$0")" || exit 1
if [ ! -x .venv/bin/python ]; then
  echo 'Please run Mac_Setup.command first.'
  read -r -p 'Press Return to close...'
  exit 1
fi
.venv/bin/python paper_renamer.py "$@"
result=$?
if [ "$result" -ne 0 ]; then read -r -p 'Press Return to close...'; fi
exit "$result"
