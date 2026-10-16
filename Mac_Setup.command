#!/bin/bash
cd -- "$(dirname -- "$0")" || exit 1
python3 setup.py
result=$?
if [ "$result" -ne 0 ]; then
  echo 'Install official Python (including Tcl/Tk) from https://www.python.org/downloads/macos/ and retry.'
fi
read -r -p 'Press Return to close...'
exit "$result"
