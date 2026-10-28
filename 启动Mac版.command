#!/bin/zsh
set -eu
cd "${0:A:h}"
if [[ ! -x .venv/bin/python ]]; then
  print '请先运行“安装Mac版.command”。'
  read -r '?按回车退出。'
  exit 1
fi
exec .venv/bin/python main.py "$@"
