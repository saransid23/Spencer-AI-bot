import pytest
from alembic.config import Config
from alembic import command
import os
import tempfile

from backend.config import settings

def test_alembic_config_loads():
    ini_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic.ini")
    assert os.path.isfile(ini_path)
    cfg = Config(ini_path)
    assert cfg.get_main_option("script_location") == "alembic"

def test_alembic_migration_files_exist():
    versions_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "alembic", "versions")
    files = os.listdir(versions_dir)
    assert any("001_initial_schema.py" in f for f in files)
