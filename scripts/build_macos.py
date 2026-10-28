"""Build locally after installing PyInstaller in this project's environment."""
import importlib.util
import json
from pathlib import Path
import subprocess
import sys

from macos_runtime import require_supported_python, runtime_info


def main():
    require_supported_python()
    if importlib.util.find_spec('PyInstaller') is None:
        raise SystemExit('请先使用项目 .venv 安装打包依赖：pip install -r requirements-macos-build.txt')
    root = Path(__file__).resolve().parents[1]
    subprocess.run([sys.executable, '-m', 'PyInstaller', '--noconfirm', '--clean',
                    str(root / 'packaging/macos.spec')], cwd=root, check=True)
    report = runtime_info()
    for repository in (root, root.parent / 'ok-script'):
        report[repository.name] = subprocess.check_output(
            ['git', '-C', str(repository), 'rev-parse', 'HEAD'], text=True).strip()
    (root / 'dist/build-info.json').write_text(json.dumps(report, indent=2) + '\n')
    print(f'构建产物：{root / "dist/OK-WW.app"}；本地产物未公证，首次运行仍需单独授权。')


if __name__ == '__main__':
    main()
