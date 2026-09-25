"""The shipped dashboard and package against the entities the integration makes."""

from __future__ import annotations

from pathlib import Path
import re

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant
from homeassistant.setup import async_setup_component
from homeassistant.util.yaml import load_yaml

ROOT = Path(__file__).parent.parent
ENTITY_ID = re.compile(r"\b(?:sensor|switch|select|number)\.[a-z0-9_]+\b")


@pytest.fixture
def expected_lingering_timers() -> bool:
    """A YAML utility meter schedules its next reset outside any config entry."""
    return True


@pytest.fixture
async def with_package(hass: HomeAssistant, init_integration: MockConfigEntry) -> None:
    """Load heat_pump_package.yaml the way the packages include does."""
    package = load_yaml(ROOT / "heat_pump_package.yaml")
    for domain, config in package.items():
        assert await async_setup_component(hass, domain, {domain: config})
    await hass.async_block_till_done()


@pytest.mark.usefixtures("with_package")
async def test_dashboard_entities_exist(hass: HomeAssistant) -> None:
    """Every entity the dashboard shows is one the setup creates."""
    dashboard = (ROOT / "heat_pump_dashboard.yaml").read_text()
    missing = sorted(
        entity_id
        for entity_id in set(ENTITY_ID.findall(dashboard))
        if hass.states.get(entity_id) is None
    )
    assert not missing


@pytest.mark.usefixtures("with_package")
async def test_package_entities(hass: HomeAssistant) -> None:
    """The package derives its sensors from the integration's."""
    assert hass.states.get("sensor.heat_pump_zone_1_activity").state == "🔥 Active"
    assert hass.states.get("sensor.heat_pump_energy_daily") is not None
