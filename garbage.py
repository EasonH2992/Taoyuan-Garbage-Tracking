import asyncio
import math
import json
import os
import requests
from playwright.async_api import async_playwright
from typing import Optional, Tuple

async def refresh_session(gid: str, routing_id: str) -> Tuple[Optional[str], Optional[str]]:
    async with async_playwright() as p:
        try:
            browser = await p.chromium.launch(headless=True)
            print("Browser launched successfully")
        except Exception as e:
            print("Browser launch error:", e)
            return None, None
        context = await browser.new_context()
        page = await context.new_page()

        await page.goto("https://route.tyoem.gov.tw/")
        await asyncio.sleep(1)

        # Click "Realtime Info" (Keep Chinese selector for website compatibility)
        await page.click("text=即時動態")
        await asyncio.sleep(1)

        # Select district
        await page.select_option("#realtime-gid", gid)
        await asyncio.sleep(1)

        # Select route
        await page.select_option("#realtime-rid", routing_id)
        await asyncio.sleep(1)

        # Click query
        await page.click("input.btn.btn-success.btn-block")
        await asyncio.sleep(3)

        # Get random_form
        random_form = await page.get_attribute("#random_form", "value")

        # Get JSESSIONID
        cookies = await context.cookies()
        jsessionid = None
        for c in cookies:
            if c['name'] == 'JSESSIONID':
                jsessionid = c['value']
                break

        await browser.close()
        return jsessionid, random_form

async def api_caller(jsessionid: str, payload: dict):
    """Generic API caller function"""
    headers = {
        "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
        "Origin": "https://route.tyoem.gov.tw",
        "Referer": "https://route.tyoem.gov.tw/",
        "X-Requested-With": "XMLHttpRequest",
        "User-Agent": "Mozilla/5.0",
    }
    session = requests.Session()
    session.cookies.set("JSESSIONID", jsessionid, domain="route.tyoem.gov.tw")

    # Run synchronous requests in a separate thread
    response = await asyncio.to_thread(
        session.post,
        "https://route.tyoem.gov.tw/web/dataManagerAgentWeb.jsp",
        headers=headers, data=payload
    )
    return response

def calculate_distance(lat1, lon1, lat2, lon2):
    """
    Calculate linear distance between two GPS coordinates using Haversine formula (meters).
    """
    R = 6371000  # 地球半徑（公尺）

    lat1_rad = math.radians(lat1)
    lon1_rad = math.radians(lon1)
    lat2_rad = math.radians(lat2)
    lon2_rad = math.radians(lon2)

    dlon = lon2_rad - lon1_rad
    dlat = lat2_rad - lat1_rad

    a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

    return R * c

def notify_ha(base_url: str, webhook_id: str, data: Optional[dict] = None):
    """Notify Home Assistant based on webhook_id"""
    webhook_url = f"{base_url}/api/webhook/{webhook_id}"
    try:
        r = requests.post(webhook_url, json=data, timeout=10)
        if r.status_code == 200:
            print(f"Successfully notified HA (Webhook: {webhook_id})")
        else:
            print(f"Failed to notify HA (Webhook: {webhook_id})", r.status_code)
    except Exception as e:
        print(f"Error notifying HA (Webhook: {webhook_id})", e)

async def main():
    # Load config
    config_path = os.path.join(os.path.dirname(__file__), 'config.json')
    if not os.path.exists(config_path):
        print("Error: config.json not found")
        return

    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)

    gid = config.get("gid")
    routing_id = config.get("routing_id")
    PROXIMITY_METERS = config.get("proximity_meters", 100)
    HA_ENTITY_WEBHOOK_ID = config.get("ha_entity_webhook_id")
    HA_BASE_URL = config.get("ha_base_url")
    TARGET_LOCATIONS = config.get("target_locations", [])

    # Initialize notified status
    for loc in TARGET_LOCATIONS:
        loc["notified"] = False

    jsessionid, random_form = await refresh_session(gid, routing_id)
    if not jsessionid or not random_form:
        print("Failed to get Session, exiting.")
        return
    print(f"Session obtained successfully")

    while True:
        car_payload = {
            "dcfid": "lagifQueryRealtimeByRoute",
            "routing_id": routing_id,
            "random_form": random_form,
        }
        try:
            resp = await api_caller(jsessionid, car_payload)
            if resp.status_code != 200:
                print(f"HTTP error {resp.status_code}, retrying...")
                await asyncio.sleep(30)
                continue

            result = resp.json()

            if result.get("errCode") == "0022":
                print("Session expired, refreshing session...")
                jsessionid, random_form = await refresh_session(gid, routing_id)
                # Reset notification status for all locations
                for loc in TARGET_LOCATIONS:
                    loc["notified"] = False
                print("All monitoring points notification status reset.")
                continue
            if result.get("errCode") == "0000":
                car_list = result.get("result", [])
                if not car_list:
                    print("No garbage truck detected on the route.")
                else:
                    # Process only the first garbage truck
                    car = car_list[0]
                    car_lat = car.get('lat')
                    car_lng = car.get('lng')
                    
                    if car_lat and car_lng:
                        print(f"--- Garbage truck detected (Car ID: {car.get('car_id')}) ---")

                        # Prepare payload for HA
                        ha_payload = {
                            "car_id": car.get('car_id'),
                            "latitude": car_lat,
                            "longitude": car_lng,
                        }

                        # Notify HA with car info on every update
                        if HA_ENTITY_WEBHOOK_ID:
                            notify_ha(HA_BASE_URL, HA_ENTITY_WEBHOOK_ID, ha_payload)

                        # Find location objects for dependency logic
                        alley_location = next((loc for loc in TARGET_LOCATIONS if loc['name'] == "Intersection"), None)
                        home_location = next((loc for loc in TARGET_LOCATIONS if loc['name'] == "Home"), None)

                        # 1. Check Intersection first
                        if alley_location and not alley_location['notified']:
                            distance = calculate_distance(alley_location['lat'], alley_location['lng'], car_lat, car_lng)
                            print(f"  -> Distance to 'Intersection': {distance:.2f} meters")
                            if distance <= PROXIMITY_METERS:
                                print(f"*** Garbage truck entering 'Intersection' within {PROXIMITY_METERS} meters! ***")
                                notify_ha(HA_BASE_URL, alley_location['webhook_id'])
                                alley_location['notified'] = True

                        # 2. Check Home only if Intersection has been notified
                        if home_location and not home_location['notified'] and alley_location and alley_location['notified']:
                            distance = calculate_distance(home_location['lat'], home_location['lng'], car_lat, car_lng)
                            print(f"  -> Distance to 'Home': {distance:.2f} meters")
                            if distance <= PROXIMITY_METERS:
                                print(f"*** Garbage truck entering 'Home' within {PROXIMITY_METERS} meters! ***")
                                notify_ha(HA_BASE_URL, home_location['webhook_id'])
                                home_location['notified'] = True
                        print("-" * 20)

            else:
                print("API returned error:", result)
        except Exception as e:
            print(f"Error during processing: {e}")

        print("Waiting 30 seconds before retry...")
        await asyncio.sleep(30)

if __name__ == "__main__":
    asyncio.run(main())
