"""The Taoyuan Garbage Truck integration."""
import asyncio
import logging
from datetime import timedelta

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .api import TaoyuanGarbageTruckAPI
from .const import (
    DOMAIN,
    CONF_GID,
    CONF_ROUTING_ID,
    CONF_ADDRESS,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_POI_ID,
    SCAN_INTERVAL_SECONDS,
)

_LOGGER = logging.getLogger(__name__)

PLATFORMS = ["sensor", "device_tracker"]

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up Taoyuan Garbage Truck from a config entry."""
    
    gid = entry.data[CONF_GID]
    routing_id = entry.data[CONF_ROUTING_ID]
    address = entry.data[CONF_ADDRESS]
    poi_id = entry.data.get(CONF_POI_ID)
    
    api = TaoyuanGarbageTruckAPI(gid, routing_id, address, poi_id)
    api.latitude = entry.data.get(CONF_LATITUDE)
    api.longitude = entry.data.get(CONF_LONGITUDE)

    coordinator = TaoyuanGarbageTruckCoordinator(hass, api)
    
    await coordinator.async_config_entry_first_refresh()

    hass.data.setdefault(DOMAIN, {})
    hass.data[DOMAIN][entry.entry_id] = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)

    return True

async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    unload_ok = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unload_ok:
        hass.data[DOMAIN].pop(entry.entry_id)

    return unload_ok

class TaoyuanGarbageTruckCoordinator(DataUpdateCoordinator):
    """Class to manage fetching Taoyuan Garbage Truck data."""

    def __init__(self, hass: HomeAssistant, api: TaoyuanGarbageTruckAPI):
        """Initialize."""
        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            update_interval=timedelta(seconds=SCAN_INTERVAL_SECONDS),
        )
        self.api = api

    async def _async_update_data(self):
        """Fetch data from API."""
        try:
            # Note: You should use async_add_executor_job if the
            # API blocks. Here we do it as it uses standard `requests`.
            data = await self.hass.async_add_executor_job(
                self.api.get_truck_data
            )
            return data
        except Exception as err:
            raise UpdateFailed(f"Error communicating with API: {err}")
