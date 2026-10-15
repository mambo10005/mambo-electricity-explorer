"""Loads packaged Markdown/YAML content."""

from importlib.resources import files
from typing import Any

import yaml

FEATURE_STATUSES = ("done", "in-progress", "planned", "dropped")


def load_yaml(name: str) -> Any:
    return yaml.safe_load(files("mambo_explorer.content").joinpath(name).read_text("utf-8"))


def features() -> list[dict[str, str]]:
    return load_yaml("features.yaml")["features"]


def learning_sequence() -> list[dict[str, str]]:
    return load_yaml("learning-sequence.yaml")["stages"]


def data_labels() -> list[dict[str, str]]:
    return load_yaml("data-labels.yaml")["labels"]
