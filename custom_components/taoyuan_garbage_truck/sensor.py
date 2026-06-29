"""Sensor platform for Taoyuan Garbage Truck."""
import logging

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
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
    """Set up the Taoyuan Garbage Truck sensors."""
    coordinator = hass.data[DOMAIN][entry.entry_id]
    unique_base = f"{entry.data[CONF_GID]}_{entry.data[CONF_ROUTING_ID]}"

    sensors = [
        TaoyuanGarbageTruckDistanceSensor(coordinator, unique_base),
        TaoyuanGarbageTruckETASensor(coordinator, unique_base),
        TaoyuanGarbageTruckStatusSensor(coordinator, unique_base, entry.data.get("address", "")),
    ]
    async_add_entities(sensors)


class TaoyuanGarbageTruckBaseSensor(CoordinatorEntity, SensorEntity):
    """Base class for Taoyuan Garbage Truck sensors."""

    def __init__(self, coordinator, unique_base):
        super().__init__(coordinator)
        self._unique_base = unique_base

    @property
    def device_info(self):
        return {
            "identifiers": {(DOMAIN, self._unique_base)},
            "name": f"Garbage Route {self._unique_base}",
            "manufacturer": "Taoyuan City",
            "model": "Garbage Truck Tracker",
        }


class TaoyuanGarbageTruckDistanceSensor(TaoyuanGarbageTruckBaseSensor):
    """Distance to the garbage truck (meters)."""

    @property
    def translation_key(self):
        return "distance"

    @property
    def unique_id(self):
        return f"{self._unique_base}_distance"

    @property
    def native_value(self):
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("distance")

    @property
    def native_unit_of_measurement(self):
        return "m"

    @property
    def device_class(self):
        return SensorDeviceClass.DISTANCE

    @property
    def state_class(self):
        return SensorStateClass.MEASUREMENT

    @property
    def icon(self):
        return "mdi:map-marker-radius-outline"


class TaoyuanGarbageTruckETASensor(TaoyuanGarbageTruckBaseSensor):
    """Estimated time of arrival for the garbage truck (minutes)."""

    @property
    def translation_key(self):
        return "eta"

    @property
    def unique_id(self):
        return f"{self._unique_base}_eta"

    @property
    def native_value(self):
        if not self.coordinator.data:
            return None
        return self.coordinator.data.get("eta")

    @property
    def native_unit_of_measurement(self):
        return "min"

    @property
    def state_class(self):
        return SensorStateClass.MEASUREMENT

    @property
    def icon(self):
        return "mdi:timer-outline"


class TaoyuanGarbageTruckStatusSensor(TaoyuanGarbageTruckBaseSensor):
    """Operational status of the garbage truck."""

    def __init__(self, coordinator, unique_base, address):
        super().__init__(coordinator, unique_base)
        self._address = address

    @property
    def translation_key(self):
        return "status"

    @property
    def unique_id(self):
        return f"{self._unique_base}_status"

    @property
    def native_value(self):
        if not self.coordinator.data:
            return "Unknown"
        return self.coordinator.data.get("status", "Unknown")

    @property
    def icon(self):
        status = self.coordinator.data.get("status") if self.coordinator.data else None
        if status == "Driving":
            return "mdi:truck-delivery"
        if status == "Not Started":
            return "mdi:truck-outline"
        if status in ("Offline", "Unknown") or status is None:
            return "mdi:truck-alert-outline"
        return "mdi:trash-can-outline"

    @property
    def extra_state_attributes(self):
        if not self.coordinator.data:
            return {}
        return {
            "car_id": self.coordinator.data.get("car_id"),
            "car_type": self.coordinator.data.get("car_type"),
            "trucks_on_route": self.coordinator.data.get("all_trucks"),
            "tracked_address": self._address,
        }
