"""Build locally after installing PyInstaller in this project's environment."""
import importlib.util
from pathlib import Path
import platform
import subprocess
import sys


def main():
    if sys.platform != 'darwin' or platform.machine() != 'arm64':
        raise SystemExit('当前构建入口面向 Apple Silicon Mac。')
    if importlib.util.find_spec('PyInstaller') is None:
        raise SystemExit('请先使用项目 .venv 安装打包依赖：pip install -r requirements-macos-build.txt')
    root = Path(__file__).resolve().parents[1]
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                    str(root / 'packaging/macos.spec')], cwd=root, check=True)
    print(f'构建产物：{root / "dist/OK-WW.app"}；本地产物未公证，首次运行仍需单独授权。')


if __name__ == '__main__':
    main()
