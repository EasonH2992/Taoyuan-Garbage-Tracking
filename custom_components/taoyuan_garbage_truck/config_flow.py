"""Config flow for Taoyuan Garbage Truck integration."""
import logging
from typing import Any, Dict, Optional

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
import homeassistant.helpers.config_validation as cv

from .api import TaoyuanGarbageTruckAPI
from .const import (
    DOMAIN,
    CONF_GID,
    CONF_ROUTING_ID,
    CONF_ADDRESS,
    CONF_LATITUDE,
    CONF_LONGITUDE,
    CONF_POI_ID,
    DEFAULT_NAME,
    DISTRICTS,
)

_LOGGER = logging.getLogger(__name__)

_TW_LAT = (21.0, 26.0)
_TW_LNG = (119.0, 123.0)


class TaoyuanGarbageTruckConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Taoyuan Garbage Truck."""

    VERSION = 1

    def __init__(self):
        self.address = None
        self.latitude = None
        self.longitude = None
        self.suggested_gid = None
        self.suggested_route = None
        self.available_routes = {}
        self.selected_route = None
        self.available_pois = []

    async def async_step_user(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> config_entries.ConfigFlowResult:
        """Step 1: address input → geocode → find nearby routes."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            self.address = user_input[CONF_ADDRESS]
            api = TaoyuanGarbageTruckAPI("", "", self.address)

            success = await self.hass.async_add_executor_job(api.geocode_address)

            if not success:
                # Geocoding failed → let user enter coordinates manually
                return await self.async_step_manual_location()

            self.latitude = api.latitude
            self.longitude = api.longitude
            return await self._async_fetch_routes(api)

        schema = vol.Schema({
            vol.Required(CONF_ADDRESS, default="桃園市桃園區建華一街"): str,
        })
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)

    async def async_step_manual_location(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> config_entries.ConfigFlowResult:
        """Step 1b: manual coordinate input when geocoding fails."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            lat = user_input[CONF_LATITUDE]
            lng = user_input[CONF_LONGITUDE]

            if not (_TW_LAT[0] <= lat <= _TW_LAT[1] and _TW_LNG[0] <= lng <= _TW_LNG[1]):
                errors["base"] = "invalid_coordinates"
            else:
                self.latitude = lat
                self.longitude = lng
                api = TaoyuanGarbageTruckAPI("", "", self.address or "")
                return await self._async_fetch_routes(api)

        schema = vol.Schema({
            vol.Required(CONF_LATITUDE): vol.Coerce(float),
            vol.Required(CONF_LONGITUDE): vol.Coerce(float),
        })
        return self.async_show_form(
            step_id="manual_location", data_schema=schema, errors=errors
        )

    async def _async_fetch_routes(self, api: TaoyuanGarbageTruckAPI):
        """Shared logic: detect district, fetch routes, go to route step."""
        for gid, dname in DISTRICTS.items():
            if dname in (self.address or ""):
                self.suggested_gid = gid
                break

        nearby = await self.hass.async_add_executor_job(
            api.get_nearby_routes, self.latitude, self.longitude
        )
        if nearby:
            best_route_id = list(nearby.keys())[0]
            self.suggested_route = best_route_id
            if not self.suggested_gid:
                self.suggested_gid = nearby[best_route_id].get("gid", "lagi2-003")

        if not self.suggested_gid:
            self.suggested_gid = "lagi2-003"

        self.available_routes = await self.hass.async_add_executor_job(
            api.get_routes_by_town, self.suggested_gid
        )
        if not self.available_routes:
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema({vol.Required(CONF_ADDRESS, default=self.address or ""): str}),
                errors={"base": "routes_not_found"},
            )
        return await self.async_step_route()

    async def async_step_route(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> config_entries.ConfigFlowResult:
        """Step 2: select route."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            self.selected_route = user_input[CONF_ROUTING_ID]
            api = TaoyuanGarbageTruckAPI(self.suggested_gid, self.selected_route, self.address or "")
            self.available_pois = await self.hass.async_add_executor_job(
                api.get_pois_by_route, self.selected_route
            )
            if not self.available_pois:
                errors["base"] = "pois_not_found"
            else:
                return await self.async_step_poi()

        route_options = {rid: f"{rname} ({rid})" for rid, rname in self.available_routes.items()}
        default_route = self.suggested_route if self.suggested_route in route_options else vol.UNDEFINED
        schema = vol.Schema({
            vol.Required(CONF_ROUTING_ID, default=default_route): vol.In(route_options),
        })
        return self.async_show_form(step_id="route", data_schema=schema, errors=errors)

    async def async_step_poi(
        self, user_input: Optional[Dict[str, Any]] = None
    ) -> config_entries.ConfigFlowResult:
        """Step 3: select specific stop (POI)."""
        errors: Dict[str, str] = {}

        if user_input is not None:
            poi_id = user_input[CONF_POI_ID]
            route_name = self.available_routes.get(self.selected_route, self.selected_route)

            if poi_id == "KEEP_ADDRESS":
                final_lat = self.latitude
                final_lng = self.longitude
                display_name = f"{DISTRICTS.get(self.suggested_gid, self.suggested_gid)} - {route_name}"
            else:
                final_lat = self.latitude
                final_lng = self.longitude
                display_name = route_name
                for p in self.available_pois:
                    if str(p.get('poi_id')) == str(poi_id):
                        final_lat = float(p.get('lat'))
                        final_lng = float(p.get('lng'))
                        display_name = f"{route_name} - {p.get('poi_name')}"
                        break

            data = {
                CONF_ADDRESS: self.address or "",
                CONF_LATITUDE: final_lat,
                CONF_LONGITUDE: final_lng,
                CONF_GID: self.suggested_gid,
                CONF_ROUTING_ID: self.selected_route,
                CONF_POI_ID: poi_id,
                CONF_NAME: display_name,
            }
            title_name = display_name.split(" - ")[-1]
            return self.async_create_entry(title=f"{DEFAULT_NAME} ({title_name})", data=data)

        poi_options = {"KEEP_ADDRESS": f"使用目前地址座標 ({self.address or self.latitude})"}
        for p in self.available_pois:
            p_id = str(p.get('poi_id'))
            poi_options[p_id] = f"{p.get('poi_name')} ({p.get('arrive_time')})"

        best_poi_id = "KEEP_ADDRESS"
        min_dist = float('inf')
        for p in self.available_pois:
            dist = TaoyuanGarbageTruckAPI._calculate_distance(
                self.latitude, self.longitude, float(p.get('lat')), float(p.get('lng'))
            )
            if dist < min_dist:
                min_dist = dist
                best_poi_id = str(p.get('poi_id'))

        default_poi = best_poi_id if best_poi_id in poi_options else vol.UNDEFINED
        schema = vol.Schema({
            vol.Required(CONF_POI_ID, default=default_poi): vol.In(poi_options),
        })
        return self.async_show_form(step_id="poi", data_schema=schema, errors=errors)
