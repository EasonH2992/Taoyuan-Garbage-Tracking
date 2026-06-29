# Taoyuan Garbage Truck — Home Assistant Integration

Track your neighborhood garbage truck in real time from Home Assistant.  
在 Home Assistant 即時追蹤桃園市垃圾車。

> Data source: [桃園市政府環境管理處垃圾清運路線即時查詢系統](https://route.tyoem.gov.tw/)  
> The same backend used by the official **桃園垃圾車** mobile app.

---

## English

### Features

- Real-time garbage truck location on the HA map
- Distance from the truck to your selected stop (meters, route-based)
- Estimated time of arrival (minutes)
- Status: Driving / Not Started / Offline
- Dynamic icons that change with truck status
- 3-step guided setup — just enter your address

### Requirements

- Home Assistant 2023.x or later
- Taoyuan City address (districts: 蘆竹、八德、桃園、中壢、平鎮、楊梅、大溪、大園、觀音、新屋、龜山、龍潭、復興)

### Installation

#### Option A — HACS (Recommended)

1. Open HACS → click the three-dot menu → **Custom repositories**
2. Add this repository URL, category **Integration**
3. Search for **Taoyuan Garbage Truck** and download
4. Restart Home Assistant

#### Option B — Manual

1. Copy the `custom_components/taoyuan_garbage_truck/` folder into your HA config directory:
   ```
   /config/custom_components/taoyuan_garbage_truck/
   ```
2. Restart Home Assistant

### Configuration

Go to **Settings → Devices & Services → Add Integration** and search for **Taoyuan Garbage Truck**.

The setup wizard has three steps:

| Step | What you do |
|---|---|
| **1 — Address** | Enter your full address, e.g. `桃園市桃園區建華一街` |
| **1b — Manual coordinates** | Only shown if address lookup fails. Paste lat/lng from Google Maps |
| **2 — Route** | Pick your garbage collection route (auto-selected to nearest) |
| **3 — Stop** | Pick the specific collection stop nearest to your home |

### Entities

After setup, four entities are created per integration entry:

| Entity | Unit | Icon | Description |
|---|---|---|---|
| `sensor.*_distance` | m | `mdi:map-marker-radius-outline` | Route-based distance to truck |
| `sensor.*_eta` | min | `mdi:timer-outline` | Estimated arrival time |
| `sensor.*_status` | — | dynamic | Driving / Not Started / Offline |
| `device_tracker.*` | — | `mdi:trash-can-outline` | Live GPS location on map |

The status icon changes dynamically:
- **Driving** → `mdi:truck-delivery`
- **Not Started** → `mdi:truck-outline`
- **Offline / Unknown** → `mdi:truck-alert-outline`

### Example Automation

Send a notification when the truck is within 200 m:

```yaml
automation:
  - alias: Garbage truck nearby
    trigger:
      - platform: numeric_state
        entity_id: sensor.taoyuan_garbage_truck_distance
        below: 200
    action:
      - service: notify.mobile_app
        data:
          message: "垃圾車快到了！預計 {{ states('sensor.taoyuan_garbage_truck_eta') }} 分鐘後抵達"
```

### Notes

- Update interval: every **30 seconds**
- The site `route.tyoem.gov.tw` uses a non-standard SSL certificate (missing Subject Key Identifier). SSL verification is disabled; a urllib3 warning suppressor is applied internally.
- This integration accesses publicly available government data. The website carries a **政府資料開放宣告** (Government Open Data Declaration).

---

## 繁體中文

### 功能

- 在 HA 地圖上即時顯示垃圾車位置
- 垃圾車到你選定清運點的距離（公尺，依路線計算）
- 預計到達時間（分鐘）
- 狀態：行駛中 / 未發車 / 離線
- 根據狀態動態切換的 icon
- 三步驟引導設定，只需輸入地址

### 系統需求

- Home Assistant 2023.x 以上
- 桃園市地址（支援行政區：蘆竹、八德、桃園、中壢、平鎮、楊梅、大溪、大園、觀音、新屋、龜山、龍潭、復興）

### 安裝

#### 方式 A — HACS（推薦）

1. 開啟 HACS → 右上角三個點 → **自訂儲存庫**
2. 填入本 repo 網址，類別選 **Integration**
3. 搜尋 **Taoyuan Garbage Truck** 並下載
4. 重啟 Home Assistant

#### 方式 B — 手動安裝

1. 將 `custom_components/taoyuan_garbage_truck/` 整個資料夾複製到 HA 設定目錄：
   ```
   /config/custom_components/taoyuan_garbage_truck/
   ```
2. 重啟 Home Assistant

### 設定

前往 **設定 → 裝置與服務 → 新增整合**，搜尋 **Taoyuan Garbage Truck**。

設定精靈共三步驟：

| 步驟 | 操作 |
|---|---|
| **1 — 地址** | 輸入完整地址，例如 `桃園市桃園區建華一街` |
| **1b — 手動輸入座標** | 只有地址解析失敗時才會出現，從 Google Maps 貼上緯度/經度 |
| **2 — 路線** | 選擇清運路線（自動預選最近的） |
| **3 — 清運點** | 選擇距離你家最近的站牌 |

### 建立的實體

每個整合設定會建立四個實體：

| 實體 | 單位 | Icon | 說明 |
|---|---|---|---|
| `sensor.*_distance` | m | `mdi:map-marker-radius-outline` | 依路線計算的車距 |
| `sensor.*_eta` | min | `mdi:timer-outline` | 預計到達時間 |
| `sensor.*_status` | — | 動態 | 行駛中 / 未發車 / 離線 |
| `device_tracker.*` | — | `mdi:trash-can-outline` | 地圖上的即時 GPS 位置 |

狀態 icon 動態切換：
- **行駛中** → `mdi:truck-delivery`
- **未發車** → `mdi:truck-outline`
- **離線 / 未知** → `mdi:truck-alert-outline`

### 自動化範例

垃圾車接近 200 公尺時發送通知：

```yaml
automation:
  - alias: 垃圾車快到了
    trigger:
      - platform: numeric_state
        entity_id: sensor.taoyuan_garbage_truck_distance
        below: 200
    action:
      - service: notify.mobile_app
        data:
          message: "垃圾車快到了！預計 {{ states('sensor.taoyuan_garbage_truck_eta') }} 分鐘後抵達"
```
---

## License

MIT
