import shutil
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixture_repo(tmp_path):
    def _copy(name: str) -> Path:
        dst = tmp_path / name
        shutil.copytree(FIXTURES / name, dst,
                        ignore=shutil.ignore_patterns("docs", ".myagent", "__pycache__"))
        return dst
    return _copy