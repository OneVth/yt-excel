"""Tests for config.yaml loading (config.py)."""

import pytest

from yt_excel.config import AppConfig, load_config


class TestLoadConfigDefaults:
    """Tests for default values when no config file exists."""

    def test_missing_file_returns_defaults(self, tmp_path):
        config = load_config(tmp_path / "nonexistent.yaml")
        assert isinstance(config, AppConfig)
        assert config.translation.model == "gpt-5-nano"
        assert config.translation.batch_size == 10
        assert config.translation.context_before == 3
        assert config.translation.context_after == 3
        assert config.translation.request_interval_ms == 200
        assert config.translation.max_retries == 3
        assert config.translation.async_enabled is True
        assert config.translation.max_concurrent_batches == 3

    def test_default_filter_values(self, tmp_path):
        config = load_config(tmp_path / "nonexistent.yaml")
        assert config.filter.min_duration_sec == 0.5
        assert config.filter.min_text_length == 2
        assert config.filter.max_duration_minutes == 15

    def test_default_file_values(self, tmp_path):
        config = load_config(tmp_path / "nonexistent.yaml")
        assert config.file.master_path == "./Master.xlsx"

    def test_default_style_values(self, tmp_path):
        config = load_config(tmp_path / "nonexistent.yaml")
        assert config.style.font == "auto"

    def test_default_ui_values(self, tmp_path):
        config = load_config(tmp_path / "nonexistent.yaml")
        assert config.ui.default_mode == "normal"


class TestLoadConfigOverride:
    """Tests for YAML values overriding defaults."""

    def test_override_translation_model(self, tmp_path):
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text('translation:\n  model: "gpt-5-mini"\n')
        config = load_config(cfg_file)
        assert config.translation.model == "gpt-5-mini"
        # Other defaults preserved
        assert config.translation.batch_size == 10

    def test_override_multiple_sections(self, tmp_path):
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            "translation:\n"
            "  model: gpt-5-mini\n"
            "  batch_size: 20\n"
            "filter:\n"
            "  min_duration_sec: 1.0\n"
            "file:\n"
            '  master_path: "./output/Master.xlsx"\n'
            "style:\n"
            '  font: "Arial"\n'
            "ui:\n"
            '  default_mode: "verbose"\n'
        )
        config = load_config(cfg_file)
        assert config.translation.model == "gpt-5-mini"
        assert config.translation.batch_size == 20
        assert config.filter.min_duration_sec == 1.0
        assert config.file.master_path == "./output/Master.xlsx"
        assert config.style.font == "Arial"
        assert config.ui.default_mode == "verbose"

    def test_partial_section_preserves_other_defaults(self, tmp_path):
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("translation:\n  max_retries: 5\n")
        config = load_config(cfg_file)
        assert config.translation.max_retries == 5
        assert config.translation.model == "gpt-5-nano"
        assert config.translation.batch_size == 10

    def test_unknown_keys_ignored(self, tmp_path):
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            "translation:\n"
            "  model: gpt-5-mini\n"
            "  unknown_field: 999\n"
            "nonexistent_section:\n"
            "  foo: bar\n"
        )
        config = load_config(cfg_file)
        assert config.translation.model == "gpt-5-mini"
        assert not hasattr(config.translation, "unknown_field")


class TestLoadConfigEdgeCases:
    """Tests for edge cases in config loading."""

    def test_empty_file_returns_defaults(self, tmp_path):
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("")
        config = load_config(cfg_file)
        assert config.translation.model == "gpt-5-nano"

    def test_yaml_with_only_comments_returns_defaults(self, tmp_path):
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("# This is a comment\n# Another comment\n")
        config = load_config(cfg_file)
        assert config.translation.model == "gpt-5-nano"

    def test_scalar_yaml_returns_defaults(self, tmp_path):
        """YAML that parses to a scalar (not dict) returns defaults."""
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("just a string\n")
        config = load_config(cfg_file)
        assert config.translation.model == "gpt-5-nano"

    def test_section_with_non_dict_value_ignored(self, tmp_path):
        """If a section is a list or scalar instead of dict, it's ignored."""
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("translation: not-a-dict\nfilter:\n  min_text_length: 5\n")
        config = load_config(cfg_file)
        assert config.translation.model == "gpt-5-nano"  # default preserved
        assert config.filter.min_text_length == 5


class TestMaxDurationMinutesConfig:
    """Tests for max_duration_minutes configuration field."""

    def test_default_value_is_15(self, tmp_path):
        config = load_config(tmp_path / "nonexistent.yaml")
        assert config.filter.max_duration_minutes == 15

    def test_override_from_yaml(self, tmp_path):
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("filter:\n  max_duration_minutes: 30\n")
        config = load_config(cfg_file)
        assert config.filter.max_duration_minutes == 30

    def test_zero_disables_check(self, tmp_path):
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("filter:\n  max_duration_minutes: 0\n")
        config = load_config(cfg_file)
        assert config.filter.max_duration_minutes == 0

    def test_preserves_other_filter_defaults(self, tmp_path):
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("filter:\n  max_duration_minutes: 60\n")
        config = load_config(cfg_file)
        assert config.filter.max_duration_minutes == 60
        assert config.filter.min_duration_sec == 0.5
        assert config.filter.min_text_length == 2


class TestAsyncTranslationConfig:
    """Tests for async translation configuration fields."""

    def test_async_enabled_default_true(self, tmp_path):
        config = load_config(tmp_path / "nonexistent.yaml")
        assert config.translation.async_enabled is True

    def test_async_enabled_override_false(self, tmp_path):
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("translation:\n  async_enabled: false\n")
        config = load_config(cfg_file)
        assert config.translation.async_enabled is False

    def test_max_concurrent_batches_default(self, tmp_path):
        config = load_config(tmp_path / "nonexistent.yaml")
        assert config.translation.max_concurrent_batches == 3

    def test_max_concurrent_batches_override(self, tmp_path):
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text("translation:\n  max_concurrent_batches: 5\n")
        config = load_config(cfg_file)
        assert config.translation.max_concurrent_batches == 5

    def test_async_fields_with_other_translation_fields(self, tmp_path):
        cfg_file = tmp_path / "config.yaml"
        cfg_file.write_text(
            "translation:\n"
            "  model: gpt-5-mini\n"
            "  async_enabled: false\n"
            "  max_concurrent_batches: 10\n"
        )
        config = load_config(cfg_file)
        assert config.translation.model == "gpt-5-mini"
        assert config.translation.async_enabled is False
        assert config.translation.max_concurrent_batches == 10
        # Other defaults preserved
        assert config.translation.batch_size == 10
        assert config.translation.max_retries == 3
