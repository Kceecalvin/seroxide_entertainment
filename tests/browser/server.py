"""Start Django for browser tests after preparing the isolated database."""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from prepare import prepare


prepare()
os.execv(
    sys.executable,
    [
        sys.executable,
        'manage.py',
        'runserver',
        '127.0.0.1:8766',
        '--settings=config.settings.browser_test',
        '--noreload',
    ],
)
