"""Install the source edition; importing this module never installs or launches."""
import argparse
import os
from pathlib import Path
import platform
import subprocess
import sys
import venv


def main():
    parser = argparse.ArgumentParser(description='安装 OK-WW Mac 源码版，不启动游戏或任务。')
    parser.add_argument('--offline', action='store_true', help='只使用本地安装包缓存')
    parser.add_argument('--wheel-dir', type=Path)
    args = parser.parse_args()
    if sys.platform != 'darwin' or platform.machine() != 'arm64' or sys.version_info[:2] != (3, 12):
        parser.error('当前锁定环境需要 Apple Silicon Mac 和 Python 3.12。')
    root = Path(__file__).resolve().parents[1]
    framework = root.parent / 'ok-script'
    if not (framework / 'ok/device/capture_methods/macos.py').is_file():
        parser.error('请把我们已改造的 ok-script 放在项目的同级目录。')
    python = root / '.venv/bin/python'
    if not python.is_file():
        venv.EnvBuilder(with_pip=True).create(root / '.venv')
    version = subprocess.check_output([str(python), '-c',
        'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")'], text=True).strip()
    if version != '3.12':
        parser.error('现有 .venv 不是 Python 3.12；请先另存旧环境，再重新安装。')
    command = [str(python), '-m', 'pip', 'install', '-r', 'requirements-macos.lock.txt']
    wheels = args.wheel_dir or root.parent / '.dependency-wheels'
    if wheels.is_dir():
        command.extend(['--find-links', str(wheels.resolve())])
    elif args.offline:
        parser.error('离线安装需要有效的 --wheel-dir 安装包目录。')
    if args.offline:
        command.append('--no-index')
    env = dict(os.environ, OK_SCRIPT_BUILD_VERSION='2.0.15')
    subprocess.run(command, cwd=root, env=env, check=True)
    subprocess.run([str(python), '-m', 'pip', 'check'], cwd=root, env=env, check=True)
    print('安装完成。双击“启动Mac版.command”打开原界面；游戏和任务均需手动启动。')


if __name__ == '__main__':
    main()
