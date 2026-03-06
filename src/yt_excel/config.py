"""Configuration loader for config.yaml with default values."""

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml


@dataclass
class TranslationConfig:
    """Translation engine settings."""

    model: str = "gpt-5-nano"
    batch_size: int = 10
    context_before: int = 3
    context_after: int = 3
    request_interval_ms: int = 200
    max_retries: int = 3
    async_enabled: bool = True
    max_concurrent_batches: int = 3


@dataclass
class FilterConfig:
    """Segment filtering settings."""

    min_duration_sec: float = 0.5
    min_text_length: int = 2


@dataclass
class FileConfig:
    """File path settings."""

    master_path: str = "./Master.xlsx"


@dataclass
class StyleConfig:
    """Excel style settings."""

    font: str = "auto"


@dataclass
class UIConfig:
    """UI display settings."""

    default_mode: str = "normal"


@dataclass
class LoggingConfig:
    """File logging settings."""

    enabled: bool = True
    dir: str = "./logs"
    level: str = "DEBUG"


@dataclass
class AppConfig:
    """Top-level application configuration."""

    translation: TranslationConfig = field(default_factory=TranslationConfig)
    filter: FilterConfig = field(default_factory=FilterConfig)
    file: FileConfig = field(default_factory=FileConfig)
    style: StyleConfig = field(default_factory=StyleConfig)
    ui: UIConfig = field(default_factory=UIConfig)
    logging: LoggingConfig = field(default_factory=LoggingConfig)


def _merge_section(dataclass_instance: Any, yaml_dict: dict[str, Any]) -> None:
    """Merge YAML dict values into a dataclass instance, ignoring unknown keys."""
    for key, value in yaml_dict.items():
        if hasattr(dataclass_instance, key):
            setattr(dataclass_instance, key, value)


def load_config(config_path: str | Path = "config.yaml") -> AppConfig:
    """Load configuration from a YAML file, falling back to defaults.

    Args:
        config_path: Path to the config.yaml file.

    Returns:
        AppConfig with values from the file merged over defaults.
        If the file doesn't exist or is empty, pure defaults are returned.
    """
    config = AppConfig()
    path = Path(config_path)

    if not path.is_file():
        return config

    with open(path, encoding="utf-8") as f:
        raw = yaml.safe_load(f)

    if not isinstance(raw, dict):
        return config

    section_map = {
        "translation": config.translation,
        "filter": config.filter,
        "file": config.file,
        "style": config.style,
        "ui": config.ui,
        "logging": config.logging,
    }

    for section_name, dataclass_instance in section_map.items():
        section_data = raw.get(section_name)
        if isinstance(section_data, dict):
            _merge_section(dataclass_instance, section_data)

    return config
