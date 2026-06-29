import logging
import math
import re

import requests
import urllib3
from bs4 import BeautifulSoup

# route.tyoem.gov.tw has a non-standard cert (missing Subject Key Identifier)
# that fails standard CA validation; suppress the noise from verify=False.
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

from .const import BASE_URL, API_URL

_LOGGER = logging.getLogger(__name__)

_SSL = False  # site cert is non-compliant, cannot use CA bundle
_HEADERS_AJAX = {"X-Requested-With": "XMLHttpRequest"}


class TaoyuanGarbageTruckAPI:
    """API client for Taoyuan Garbage Truck."""

    def __init__(self, gid: str, routing_id: str, address: str, poi_id: str = None):
        self.gid = gid
        self.routing_id = routing_id
        self.address = address
        self.poi_id = poi_id
        self.latitude = None
        self.longitude = None

        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        })
        self.random_form = None

        self.BASELINE_SPEED = 1.0  # m/s
        self.WEIGHT_BASELINE = 0.75
        self.path = None
        self.home_idx = None
        self.home_t = None

    def geocode_address(self) -> bool:
        """Convert address to coordinates via Nominatim with Taiwan-specific fallbacks."""
        try:
            from geopy.geocoders import Nominatim
            geolocator = Nominatim(user_agent="taoyuan_garbage_truck_ha")

            for query in self._address_fallbacks(self.address):
                location = geolocator.geocode(query)
                if location:
                    self.latitude = location.latitude
                    self.longitude = location.longitude
                    _LOGGER.info("Resolved '%s' → (%s, %s)", self.address, self.latitude, self.longitude)
                    return True

            _LOGGER.error("Could not resolve address: %s", self.address)
            return False
        except Exception as e:
            _LOGGER.error("Error resolving address: %s", e)
            return False

    @staticmethod
    def _address_fallbacks(address: str) -> list:
        """Generate progressively simpler queries for a Taiwan address."""
        candidates = [address]
        stripped = re.sub(r'\d+號|\d+弄|\d+巷|\d+樓|\d+-?\d+號', '', address)
        if stripped != address:
            candidates.append(stripped)
        m = re.search(r'(.*?市.*?區.*?(路|街|段))', address)
        if m:
            candidates.append(m.group(1))
        m2 = re.search(r'(.*?市.*?區)', address)
        if m2:
            candidates.append(m2.group(1))
        return candidates

    def update_session(self) -> bool:
        """Fetch a new JSESSIONID and random_form token."""
        try:
            resp = self.session.get(BASE_URL, verify=_SSL, timeout=10)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, 'html.parser')
            tag = soup.find('input', id='random_form')
            if tag:
                self.random_form = tag.get('value')
                _LOGGER.debug("Session refreshed.")
                return True
            _LOGGER.error("random_form not found in HTML")
            return False
        except Exception as e:
            _LOGGER.error("Failed to update session: %s", e)
            return False

    def _ensure_session(self) -> bool:
        if not self.random_form:
            return self.update_session()
        return True

    def _post(self, payload: dict) -> dict:
        """POST to the API endpoint, return parsed JSON or {}."""
        try:
            resp = self.session.post(
                API_URL, data=payload, headers=_HEADERS_AJAX,
                verify=_SSL, timeout=10,
            )
            resp.raise_for_status()
            return resp.json()
        except Exception as e:
            _LOGGER.error("API request failed: %s", e)
            return {}

    def get_routes_by_town(self, gid: str) -> dict:
        """Return {routing_id: routing_name} for a district."""
        if not self._ensure_session():
            return {}
        data = self._post({"dcfid": "lagifQueryRouteByTown", "gid": gid, "random_form": self.random_form})
        routes = {}
        for r in data.get('result', []):
            rid = r.get('routing_id')
            if rid:
                routes[rid] = r.get('routing_name', rid)
        return routes

    def get_nearby_routes(self, lat: float, lng: float) -> dict:
        """Return {routing_id: {routing_name, gid}} near a location."""
        if not self._ensure_session():
            return {}
        data = self._post({
            "dcfid": "lagifPoiNearByLoc2",
            "lat": lat, "lng": lng,
            "range": 300, "cartype": "lagi",
            "random_form": self.random_form,
        })
        routes = {}
        for r in data.get('result', []):
            rid = r.get('routing_id')
            if rid and rid not in routes:
                gid = r.get('gid') or rid.split('_')[0]
                routes[rid] = {"routing_name": r.get('routing_name'), "gid": gid}
        return routes

    def get_pois_by_route(self, routing_id: str) -> list:
        """Return list of POI dicts for a route."""
        if not self._ensure_session():
            return []
        data = self._post({
            "dcfid": "lagifQueryTimeTableDetailByRoute",
            "routing_id": routing_id,
            "car_type": "lagi",
            "random_form": self.random_form,
        })
        pois = []
        for p in data.get('result', []):
            if p.get('poi_name') and p.get('lat') and p.get('lng'):
                pois.append({
                    "poi_id": p.get('poi_id'),
                    "poi_name": p.get('poi_name'),
                    "lat": float(p.get('lat')),
                    "lng": float(p.get('lng')),
                    "arrive_time": p.get('arrive_time'),
                    "est_time": p.get('est_time', '-'),
                })
        return pois

    def _fetch_routing_path(self):
        """Fetch the polyline of the route and store it in self.path."""
        if not self._ensure_session():
            return
        data = self._post({
            "dcfid": "poiTraceByRoute",
            "routing_id": self.routing_id,
            "random_form": self.random_form,
        })
        for r in data.get('result', []):
            path_str = r.get('routing_path')
            if path_str:
                points = []
                for pt in path_str.split('|'):
                    if pt and ',' in pt:
                        parts = pt.split(',')
                        points.append((float(parts[0]), float(parts[1])))
                self.path = points
                break

    def get_truck_data(self, _session_refreshed: bool = False) -> dict:
        """Fetch current truck positions and calculate distance/ETA."""
        if not self._ensure_session():
            return {}

        data = self._post({
            "dcfid": "lagifQueryRealtimeByRoute",
            "routing_id": self.routing_id,
            "random_form": self.random_form,
            "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        })

        if data.get("errCode") == "0022":
            if _session_refreshed:
                _LOGGER.error("Session refresh failed, giving up.")
                return {}
            _LOGGER.info("Session expired, refreshing...")
            self.random_form = None
            return self.get_truck_data(_session_refreshed=True)

        if data.get("errCode") != "0000":
            _LOGGER.error("API error: %s", data)
            return {}

        trucks = data.get("result", [])
        if not trucks:
            return {"status": "No trucks on route", "distance": None, "eta": None}

        main_truck = next((t for t in trucks if t.get("car_type") == "垃圾車"), trucks[0])
        truck_lat = main_truck.get("lat")
        truck_lng = main_truck.get("lng")

        if not truck_lat or not truck_lng or not self.latitude or not self.longitude:
            return {"status": "Missing coordinates", "distance": None, "eta": None}

        # Route-based distance calculation
        if self.path is None:
            self._fetch_routing_path()
            if self.path:
                self.home_idx, self.home_t, _ = self._find_closest_segment(self.latitude, self.longitude)

        if self.path and self.home_idx is not None:
            t_idx, t_t, _ = self._find_closest_segment(truck_lat, truck_lng)
            if t_idx < self.home_idx or (t_idx == self.home_idx and t_t <= self.home_t):
                distance = self._calc_route_distance(t_idx, t_t, self.home_idx, self.home_t)
            else:
                distance = 0.0
        else:
            distance = self._calculate_distance(self.latitude, self.longitude, truck_lat, truck_lng)

        raw_status = main_truck.get("status", "Unknown")
        status = "Driving" if raw_status == "行駛中" else raw_status
        clean_status = main_truck.get("clean_status", "")
        is_offline = "未發車" in clean_status or "不在站" in clean_status

        poi_eta = None
        if self.poi_id:
            for p in self.get_pois_by_route(self.routing_id):
                if str(p.get('poi_id')) == str(self.poi_id):
                    est = p.get('est_time')
                    if est and est != "-":
                        try:
                            poi_eta = int(est)
                        except (ValueError, TypeError):
                            pass
                    else:
                        is_offline = True
                    break

        if is_offline:
            status = "Not Started" if "未發車" in clean_status else "Offline"
            distance = None
            eta_minutes = None
        else:
            eta_minutes = poi_eta if poi_eta is not None else math.ceil((distance / self.BASELINE_SPEED) / 60)

        return {
            "status": status,
            "distance": round(distance, 1) if distance is not None else None,
            "eta": eta_minutes,
            "car_id": main_truck.get("car_id"),
            "car_type": main_truck.get("car_type"),
            "latitude": truck_lat,
            "longitude": truck_lng,
            "all_trucks": len(trucks),
        }

    # ── Geometry helpers ──────────────────────────────────────────────────────

    @staticmethod
    def _calculate_distance(lat1, lon1, lat2, lon2) -> float:
        """Haversine distance in meters."""
        R = 6371000
        lat1_r, lon1_r = math.radians(lat1), math.radians(lon1)
        lat2_r, lon2_r = math.radians(lat2), math.radians(lon2)
        dlat = lat2_r - lat1_r
        dlon = lon2_r - lon1_r
        a = math.sin(dlat / 2) ** 2 + math.cos(lat1_r) * math.cos(lat2_r) * math.sin(dlon / 2) ** 2
        return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    @staticmethod
    def _point_to_segment_dist(p_lat, p_lng, a_lat, a_lng, b_lat, b_lng):
        lat_m = 111320
        lng_m = 40075000 * math.cos(math.radians((a_lat + b_lat) / 2)) / 360
        px, py = p_lng * lng_m, p_lat * lat_m
        ax, ay = a_lng * lng_m, a_lat * lat_m
        bx, by = b_lng * lng_m, b_lat * lat_m
        l2 = (ax - bx) ** 2 + (ay - by) ** 2
        if l2 == 0:
            return math.sqrt((px - ax) ** 2 + (py - ay) ** 2), 0
        t = max(0, min(1, ((px - ax) * (bx - ax) + (py - ay) * (by - ay)) / l2))
        proj_x = ax + t * (bx - ax)
        proj_y = ay + t * (by - ay)
        return math.sqrt((px - proj_x) ** 2 + (py - proj_y) ** 2), t

    def _find_closest_segment(self, lat, lng):
        if not self.path or len(self.path) < 2:
            return 0, 0, float('inf')
        min_dist = float('inf')
        best_idx = best_t = 0
        for i in range(len(self.path) - 1):
            a, b = self.path[i], self.path[i + 1]
            dist, t = self._point_to_segment_dist(lat, lng, a[0], a[1], b[0], b[1])
            if dist < min_dist:
                min_dist, best_idx, best_t = dist, i, t
        return best_idx, best_t, min_dist

    def _calc_route_distance(self, start_idx, start_t, end_idx, end_t) -> float:
        if start_idx > end_idx or (start_idx == end_idx and start_t >= end_t):
            return 0.0
        dist = 0.0
        if start_idx == end_idx:
            p1, p2 = self.path[start_idx], self.path[start_idx + 1]
            return self._calculate_distance(p1[0], p1[1], p2[0], p2[1]) * (end_t - start_t)
        p1, p2 = self.path[start_idx], self.path[start_idx + 1]
        dist += self._calculate_distance(p1[0], p1[1], p2[0], p2[1]) * (1.0 - start_t)
        for i in range(start_idx + 1, end_idx):
            dist += self._calculate_distance(self.path[i][0], self.path[i][1], self.path[i + 1][0], self.path[i + 1][1])
        pn1, pn2 = self.path[end_idx], self.path[end_idx + 1]
        dist += self._calculate_distance(pn1[0], pn1[1], pn2[0], pn2[1]) * end_t
        return dist
