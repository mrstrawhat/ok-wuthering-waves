"""Run a bounded native macOS function with the local ok-script checkout."""
import argparse
import os
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
framework = Path(os.environ.get('OK_SCRIPT_PATH', ROOT.parent / 'ok-script')).resolve()
if not (framework / 'ok').is_dir():
    raise SystemExit('Set OK_SCRIPT_PATH to your local ok-script checkout')
sys.path.insert(0, str(framework))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('function', choices=['close-menu'])
    parser.add_argument('--output', type=Path, default=ROOT.parent / 'macOS改造验收记录' /
                        'T006' / datetime.now().strftime('run-%H%M%S'))
    args = parser.parse_args()
    from src.task.MacMenuTask import MacMenuTask
    MacMenuTask(ROOT / 'assets/coco_annotations.json').run(args.output)


if __name__ == '__main__':
    main()
