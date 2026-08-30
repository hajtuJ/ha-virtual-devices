"""Static integration scaffold tests."""

import json
from pathlib import Path

from custom_components.virtual_devices.const import DOMAIN

INTEGRATION_DIR = Path("custom_components") / DOMAIN


def test_manifest_has_required_custom_integration_metadata() -> None:
    """Test required manifest metadata and domain consistency."""
    manifest = json.loads((INTEGRATION_DIR / "manifest.json").read_text())

    assert manifest["domain"] == DOMAIN
    assert manifest["config_flow"] is True
    assert manifest["integration_type"] == "helper"
    assert manifest["iot_class"] == "calculated"
    assert manifest["version"] == "0.1.0"


def test_translation_structures_match_strings() -> None:
    """Test that required translations have the same object structure."""
    strings = json.loads((INTEGRATION_DIR / "strings.json").read_text())

    def shape(value: object) -> object:
        if isinstance(value, dict):
            return {key: shape(child) for key, child in value.items()}
        return None

    expected_shape = shape(strings)
    for language in ("en", "pl"):
        translation = json.loads(
            (INTEGRATION_DIR / "translations" / f"{language}.json").read_text()
        )
        assert shape(translation) == expected_shape
