"""Shared test fixtures for CABT extraction tests."""
import sys
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def sys_path_setup():
    """Add cabt-cc/scripts/ to sys.path so extract_epub can be imported."""
    scripts_dir = str(Path(__file__).parent.parent / "cabt-cc" / "scripts")
    if scripts_dir not in sys.path:
        sys.path.insert(0, scripts_dir)


@pytest.fixture
def test_epub_path():
    """Path to the test EPUB file."""
    epub_path = Path(__file__).parent / "data" / "test-book.epub"
    assert epub_path.is_file(), f"Test EPUB not found at {epub_path}"
    return epub_path


@pytest.fixture
def tmp_output_dir(tmp_path):
    """Temporary output directory for extraction tests."""
    output_dir = tmp_path / "extraction_output"
    output_dir.mkdir()
    return output_dir


@pytest.fixture
def workspace_args():
    """Standard test arguments for workspace creation."""
    return {
        "genre": "General",
        "source_language": "English",
        "target_language": "French",
    }
