"""Shared interpreter requirement for source installation and app builds."""
import platform
import sys

def require_supported_python():
    if sys.platform != 'darwin' or platform.machine() != 'arm64':
        raise SystemExit('当前环境需要 Apple Silicon Mac。')
    if sys.version_info[:2] != (3, 12):
        raise SystemExit('请使用与锁定依赖配套的 Python 3.12。')


def runtime_info():
    return {'python_version': platform.python_version(), 'executable': sys.executable,
            'base_executable': getattr(sys, '_base_executable', sys.executable),
            'base_prefix': sys.base_prefix, 'machine': platform.machine()}
