#!/bin/zsh
set -eu
cd "${0:A:h}"
python_bin="${OKWW_PYTHON:-}"
if [[ -z "$python_bin" ]]; then
  if [[ -x .venv/bin/python ]]; then
    python_bin="$PWD/.venv/bin/python"
  elif [[ -x /opt/homebrew/bin/python3.12 ]]; then
    python_bin=/opt/homebrew/bin/python3.12
  else
    python_bin="$(command -v python3.12 || true)"
  fi
fi
if [[ -z "$python_bin" ]]; then
  print '请先安装 Python 3.12（Apple Silicon），或通过 OKWW_PYTHON 指定解释器。'
  read -r '?按回车退出。'
  exit 1
fi
"$python_bin" scripts/install_macos.py "$@"
