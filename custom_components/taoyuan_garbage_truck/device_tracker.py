"""Device tracker platform for Taoyuan Garbage Truck."""
import logging

from homeassistant.components.device_tracker import SourceType, TrackerEntity
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN, CONF_GID, CONF_ROUTING_ID

_LOGGER = logging.getLogger(__name__)

async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up the Taoyuan Garbage Truck device tracker."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    unique_base = f"{entry.data[CONF_GID]}_{entry.data[CONF_ROUTING_ID]}"

    async_add_entities([TaoyuanGarbageTruckTracker(coordinator, unique_base)])


class TaoyuanGarbageTruckTracker(CoordinatorEntity, TrackerEntity):
    """Device tracker for Taoyuan Garbage Truck."""

    def __init__(self, coordinator, unique_base):
        """Initialize the tracker."""
        super().__init__(coordinator)
        self._unique_base = unique_base

    @property
    def translation_key(self):
        """Return the translation key."""
        return "tracker"

    @property
    def unique_id(self):
        """Return a unique ID to use for this entity."""
        return f"{self._unique_base}_tracker"

    @property
    def latitude(self):
        """Return latitude value of the device."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("latitude")

    @property
    def longitude(self):
        """Return longitude value of the device."""
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("longitude")

    @property
    def source_type(self):
        """Return the source type, eg gps or router, of the device."""
        return SourceType.GPS

    @property
    def icon(self):
        """Return the icon of the tracker."""
        return "mdi:trash-can-outline"

    @property
    def device_info(self):
        """Return device information about this entity."""
        return {
            "identifiers": {(DOMAIN, self._unique_base)},
            "name": f"Garbage Route {self._unique_base}",
            "manufacturer": "Taoyuan City",
            "model": "Garbage Truck Tracker",
        }

    @property
    def extra_state_attributes(self):
        """Return the state attributes."""
        if not self.coordinator.data:
            return {}
        return {
            "car_id": self.coordinator.data.get("car_id"),
            "car_type": self.coordinator.data.get("car_type"),
            "status": self.coordinator.data.get("status"),
        }
