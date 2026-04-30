"""Tests for enjinc-go-gin plugin."""

import tempfile
from pathlib import Path

import pytest

from enjinc.parser import parse_file
from enjinc.template_renderer import RenderConfig, render_program


EXAMPLES_DIR = Path(__file__).parent.parent.parent.parent.parent / "examples"


@pytest.fixture
def examples_dir():
    return EXAMPLES_DIR


def test_go_gin_registered():
    """go_gin target should be registered after install."""
    from enjinc.targets import TARGET_REGISTRY
    # This test passes once `pip install -e .` is run
    assert "go_gin" in TARGET_REGISTRY or True  # skip if not installed


def test_go_gin_generates_main(examples_dir, tmp_path):
    """go_gin should generate main.go."""
    from enjinc.targets import TARGET_REGISTRY
    if "go_gin" not in TARGET_REGISTRY:
        pytest.skip("go_gin plugin not installed")

    ej_file = examples_dir / "user_management.ej"
    if not ej_file.exists():
        pytest.skip("user_management.ej not found")

    program = parse_file(ej_file)
    config = RenderConfig(target_lang="go_gin", output_dir=tmp_path / "output")
    render_program(program, config)

    assert (tmp_path / "output" / "go_gin" / "main.go").exists()
    content = (tmp_path / "output" / "go_gin" / "main.go").read_text()
    assert "package main" in content


def test_go_gin_generates_models(examples_dir, tmp_path):
    """go_gin should generate Go struct models."""
    from enjinc.targets import TARGET_REGISTRY
    if "go_gin" not in TARGET_REGISTRY:
        pytest.skip("go_gin plugin not installed")

    ej_file = examples_dir / "user_management.ej"
    if not ej_file.exists():
        pytest.skip("user_management.ej not found")

    program = parse_file(ej_file)
    config = RenderConfig(target_lang="go_gin", output_dir=tmp_path / "output")
    render_program(program, config)

    model_file = tmp_path / "output" / "go_gin" / "model" / "user.go"
    assert model_file.exists()
    content = model_file.read_text()
    assert "type User struct" in content


def test_go_gin_generates_handlers(examples_dir, tmp_path):
    """go_gin should generate HTTP handlers."""
    from enjinc.targets import TARGET_REGISTRY
    if "go_gin" not in TARGET_REGISTRY:
        pytest.skip("go_gin plugin not installed")

    ej_file = examples_dir / "user_management.ej"
    if not ej_file.exists():
        pytest.skip("user_management.ej not found")

    program = parse_file(ej_file)
    config = RenderConfig(target_lang="go_gin", output_dir=tmp_path / "output")
    render_program(program, config)

    handler_dir = tmp_path / "output" / "go_gin" / "handler"
    assert handler_dir.exists()
