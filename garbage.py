import asyncio
import math
import json
import os
import requests
import time
from playwright.async_api import async_playwright
from typing import Optional, Tuple

# --- 這是針對「垃圾車」特調的參數 ---
# 根據你的數據：650m / 7min ≈ 1.55 m/s
# 我們設定這個基準，強迫程式一開始用這個速度去估算
BASELINE_SPEED = 1.0  
# 權重：0.0 到 1.0
# 0.7 代表：ETA 的計算 70% 相信「基準慢速」，30% 相信「現在的車速」
# 這樣就算它起步很快，ETA 也不會瞬間變成 1 分鐘
WEIGHT_BASELINE = 0.75

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

        # Close the announcement modal
        try:
            # Click on a blank area (top-left corner) to dismiss the modal
            await page.mouse.click(10, 10)
            await asyncio.sleep(1)
        except Exception:
            print("Error attempting to close modal, continuing...")

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

    # ETA variables
    eta_checkpoint = next((loc for loc in TARGET_LOCATIONS if loc['name'] == "eta_checkpoint"), None)
    eta_active = False
    traveled_distance = 0.0
    checkpoint_start_time = 0.0
    last_lat = None
    last_lng = None

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
                # Reset ETA
                eta_active = False
                traveled_distance = 0.0
                last_lat = None
                last_lng = None
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
                        # Calculate step distance for ETA
                        step_dist = 0.0
                        if last_lat is not None and last_lng is not None:
                            step_dist = calculate_distance(last_lat, last_lng, car_lat, car_lng)
                        last_lat = car_lat
                        last_lng = car_lng

                        # Check ETA Checkpoint
                        if eta_checkpoint and not eta_active:
                            dist_cp = calculate_distance(eta_checkpoint['lat'], eta_checkpoint['lng'], car_lat, car_lng)
                            if dist_cp <= PROXIMITY_METERS:
                                print("--- Reached ETA Checkpoint, starting ETA calculation ---")
                                eta_active = True
                                checkpoint_start_time = time.time()
                                traveled_distance = 0.0

                        # Calculate ETA
                        eta_minutes = None
                        if eta_active:
                            traveled_distance += step_dist
                            remaining_dist = max(0, 1200 - traveled_distance)
                            elapsed = time.time() - checkpoint_start_time

                            if elapsed > 1 and traveled_distance > 0:
                                # 1. 計算當前這趟的實際平均速度 (Real-time average)
                                current_real_avg = traveled_distance / elapsed
                                
                                # 2. 計算「混合速度」 (Blended Speed)
                                # 公式：(基準速度 * 權重) + (實際速度 * (1 - 權重))
                                # 剛開始時，這個公式會把過快的速度「拉低」
                                calc_speed = (BASELINE_SPEED * WEIGHT_BASELINE) + (current_real_avg * (1 - WEIGHT_BASELINE))
                                
                                # 3. 計算 ETA
                                eta_seconds = remaining_dist / calc_speed
                                eta_minutes = math.ceil(eta_seconds / 60)
                                
                                # (除錯用：你可以把這行印出來看，會發現 calc_speed 比實際速度慢很多，這就是我們要的)
                                print(f"實際速度: {current_real_avg:.2f}, 修正後計算速度: {calc_speed:.2f}")

                            else:
                                # 剛開始完全沒有數據時，直接用最保守的基準速度算
                                eta_minutes = math.ceil(remaining_dist / BASELINE_SPEED / 60)

                        print(f"--- Garbage truck detected (Car ID: {car.get('car_id')}) ---")

                        # Prepare payload for HA
                        ha_payload = {
                            "car_id": car.get('car_id'),
                            "latitude": car_lat,
                            "longitude": car_lng,
                        }
                        
                        if eta_minutes is not None:
                            ha_payload["eta_minutes"] = eta_minutes
                            print(f"  -> ETA: {eta_minutes} min (Traveled: {traveled_distance:.0f}m)")
                        # Notify HA with car info on every update
                        if HA_ENTITY_WEBHOOK_ID:
                            notify_ha(HA_BASE_URL, HA_ENTITY_WEBHOOK_ID, ha_payload)

                        # Find location objects for dependency logic
                        checkpoint_location = next((loc for loc in TARGET_LOCATIONS if loc['name'] == "eta_checkpoint"), None)
                        alley_location = next((loc for loc in TARGET_LOCATIONS if loc['name'] == "Intersection"), None)
                        home_location = next((loc for loc in TARGET_LOCATIONS if loc['name'] == "Home"), None)

                        # 1. Check Intersection first
                        if not eta_active:
                            distance = calculate_distance(checkpoint_location['lat'], checkpoint_location['lng'], car_lat, car_lng)
                            print(f"  -> Distance to 'Checkpoint': {distance:.2f} meters")
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
                        
                        # Stop ETA if Home reached
                        if home_location and home_location['notified']:
                            eta_active = False

                        print("-" * 20)

            else:
                print("API returned error:", result)
        except Exception as e:
            print(f"Error during processing: {e}")

        print("Waiting 15 seconds before retry...")
        await asyncio.sleep(15)

if __name__ == "__main__":
    asyncio.run(main())