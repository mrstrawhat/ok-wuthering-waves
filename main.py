if __name__ == '__main__':
    import os
    import sys
    from pathlib import Path

    if sys.platform == 'darwin':
        if getattr(sys, 'frozen', False):
            data_dir = Path(os.environ.get('OKWW_DATA_DIR') or
                            Path.home() / 'Library' / 'Application Support' / 'OK-WW').expanduser().resolve()
            data_dir.mkdir(parents=True, exist_ok=True)
            os.chdir(data_dir)
        else:
            os.chdir(Path(__file__).resolve().parent)
    from config import config
    from ok import OK

    config = config
    ok = OK(config)
    ok.start()
