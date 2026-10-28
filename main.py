if __name__ == '__main__':
    import os
    import sys
    from pathlib import Path

    if sys.platform == 'darwin':
        os.chdir(Path(__file__).resolve().parent)
    from config import config
    from ok import OK

    config = config
    ok = OK(config)
    ok.start()
