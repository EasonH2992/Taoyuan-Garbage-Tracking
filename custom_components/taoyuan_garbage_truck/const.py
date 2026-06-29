"""Constants for the Taoyuan Garbage Truck integration."""

DOMAIN = "taoyuan_garbage_truck"

CONF_GID = "gid"
CONF_ROUTING_ID = "routing_id"
CONF_ADDRESS = "address"
CONF_LATITUDE = "latitude"
CONF_LONGITUDE = "longitude"
CONF_POI_ID = "poi_id"

DEFAULT_NAME = "Taoyuan Garbage Truck"

# Update frequency
SCAN_INTERVAL_SECONDS = 30

# API Endpoints
BASE_URL = "https://route.tyoem.gov.tw"
API_URL = "https://route.tyoem.gov.tw/web/dataManagerAgentWeb.jsp"

# Map district names to GIDs
DISTRICTS = {
    "lagi2-001": "蘆竹區",
    "lagi2-002": "八德區",
    "lagi2-003": "桃園區",
    "lagi2-004": "中壢區",
    "lagi2-005": "平鎮區",
    "lagi2-006": "楊梅區",
    "lagi2-007": "大溪區",
    "lagi2-008": "大園區",
    "lagi2-009": "觀音區",
    "lagi2-010": "新屋區",
    "lagi2-011": "龜山區",
    "lagi2-012": "龍潭區",
    "lagi2-013": "復興區",
}
