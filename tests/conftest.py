import shutil
from pathlib import Path

import pytest

EXAMPLES = Path(__file__).resolve().parent.parent / "jobhunter" / "examples"


@pytest.fixture
def workspace(tmp_path):
    """Рабочая папка с примерами config.yaml и profile.yaml."""
    shutil.copy(EXAMPLES / "config.example.yaml", tmp_path / "config.yaml")
    shutil.copy(EXAMPLES / "profile.example.yaml", tmp_path / "profile.yaml")
    (tmp_path / "resume").mkdir()
    return tmp_path


@pytest.fixture
def settings(workspace):
    from jobhunter.config import load_settings
    return load_settings(workspace)


@pytest.fixture
def matcher(settings):
    from jobhunter.matching import Matcher
    from jobhunter.profile.schema import load_profile
    return Matcher(load_profile(settings.profile_path), settings.matching)
