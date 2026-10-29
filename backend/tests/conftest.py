"""Gives every test a fresh, throw-away database filled by seed.py,
so running the tests never touches your real dept.db."""
import os
import sys

import pytest
from fastapi.testclient import TestClient

BACKEND = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)           # dept.db is created in a temporary folder
    monkeypatch.syspath_prepend(BACKEND)  # so `import main` finds backend/main.py
    for name in ("main", "seed"):         # fresh import = fresh database for every test
        sys.modules.pop(name, None)
    import main
    import seed  # noqa: F401  (running it fills the new database)
    with TestClient(main.app) as c:
        yield c
