# AVNCodex Indexer API Reference

This document provides instructions for developers interacting with the AVNCodex Indexer API. It covers setup, endpoints, and a detailed dictionary of the data structures returned.

## 🚀 Getting Started

### Base URL
The API typically runs on port `8000` (Dev) or `5005` (Prod/Docker).
- **Base URL**: `http://localhost:8000`
- **Swagger UI** (Interactive Docs): `http://localhost:8000/docs`
- **ReDoc**: `http://localhost:8000/redoc`

### Authentication
Currently, the API is **public** and does not require authentication. Ensure it is not exposed to the open internet without a reverse proxy or firewall.

---

## 📡 Endpoints

### 1. Search Games
Search for a game by name or browse the local library with filters.
- **Method**: `GET`
- **Endpoint**: `/games/search`
- **Behavior**:
    - **With `q`**: Performs a **Remote Search** (F95Zone) to fetch fresh data, upserts it to the Local DB, then returns filtered results from the Local DB.
    - **Without `q`**: Browses/Filters the **Local DB** only.
- **Params**: 
    - `q` (string, optional): The search query (e.g., "Eternum").
    - `creator` (string, optional): Filter by Creator/Author (partial match). (e.g., `creator=DrPinkCake`).
    - `status` (list[string], optional): Filter by **Status ID/Name** (Inclusion). (e.g., `status=Completed&status=Ongoing` or `status=1`).
    - `exclude_status` (list[string], optional): Filter by **Status ID/Name** (Exclusion). (e.g., `exclude_status=Abandoned`).
    - `engine` (list[int], optional): Filter by **Type ID** (Inclusion). (e.g., `engine=14&engine=19`).
    - `exclude_engine` (list[int], optional): Filter by **Type ID** (Exclusion). (e.g., `exclude_engine=4`).
    - `tags` (list[string], optional): Filter by **Tag Name** (Precise JSON match). (e.g., `tags=RPG&tags=Fantasy`).
    - `tag_mode` (string, optional): Logic for `tags` list. `AND` (default) or `OR`.
    - `tag_groups` (string, optional): **Advanced**. JSON string for groups logic: `(G1) OR (G2)`. Example: `[["RPG", "Fantasy"], ["Strategy"]]` means `(RPG AND Fantasy) OR Strategy`.
    - `exclude_tags` (list[string], optional): Filter by **Excluding** Tag Name. (e.g., `exclude_tags=Netorare`).
    - `updated_after` (string, optional): Filter for games updated after this date (ISO 8601, e.g., "2024-01-01").
    - `page` (int, optional): Page number (default: 1).
    - `limit` (int, optional): Items per page (default: 30, max: 100).
    - `sort_by` (string, optional): Sort field (`name`, `updated_at`, `rating`, `likes`). Default: `updated_at`.
    - `sort_dir` (string, optional): Sort direction (`asc`, `desc`). Default: `desc`.
- **Example (Advanced)**:
    - *Query 1*: Engine = RenPy, Tag = RPG OR Strategy, Status = Ongoing
    - *URL 1*: `/games/search?engine=14&status=1&tags=RPG&tags=Strategy&tag_mode=OR`
    - *Query 2 (Complex)*: (Action AND Adventure) OR (Strategy)
    - *URL 2*: `/games/search?tag_groups=%5B%5B%22Action%22%2C%22Adventure%22%5D%2C%5B%22Strategy%22%5D%5D`
- **Returns**: JSON Array of [Game Objects](#game-object-model).

### 2. Get Game Details
Retrieve cached data for a specific game by its F95Zone Thread ID.
- **Method**: `GET`
- **Endpoint**: `/games/{game_id}`
- **Returns**: [Game Object](#game-object-model) or 404.

### 3. Track Game (Important)
Mark a game as "Tracked". This prioritizes it for updates and immediately fetches detailed metadata (including download links) from F95Checker.
- **Method**: `POST`
- **Endpoint**: `/games/{game_id}/track`
- **Returns**: Updated [Game Object](#game-object-model).
- **Side Effect**: Triggers immediate background sync for this game.

### 4. Untrack Game
Stop tracking a game.
- **Method**: `POST`
- **Endpoint**: `/games/{game_id}/untrack`
- **Returns**: Updated [Game Object](#game-object-model) with `tracked=false`.

### 5. Force Refresh
Manually force a sync for a specific game from upstream sources.
- **Method**: `POST`
- **Endpoint**: `/games/{game_id}/refresh`
- **Returns**: Updated [Game Object](#game-object-model).

### 6. Trigger Global Update
Manually trigger the scheduled task that checks for all updates.
- **Method**: `POST`
- **Endpoint**: `/games/trigger-update`
- **Returns**: JSON Status.

### 7. Trigger Seeding
Trigger the alphabetical background seeding task. This scrapes F95Zone alphabetically to populate the index.
- **Method**: `POST`
- **Endpoint**: `/games/seed`
- **Returns**: JSON Status.
- **Example**: Invoke-RestMethod -Method Post -Uri "http://192.168.200.16:5005/games/seed"

### 8. Get Seeding Status
Get the current status of the background seeding process.
- **Method**: `GET`
- **Endpoint**: `/games/seed`
- **Returns**: JSON Object.
    - `is_running` (boolean)
    - `current_page` (integer)
    - `items_processed` (integer)
    - `last_error` (string or null)
    - `pending_enrichment_count` (integer): Number of games waiting for enrichment details.
    - `estimated_seconds_remaining` (integer): Estimated time to complete enrichment (based on current queue).

---

## 💾 Data Models

### Game Object Model
The core response object representing a game.

| Field | Type | Description |
| :--- | :--- | :--- |
| `f95_id` | Integer | The F95Zone Thread ID (Unique Identifier). |
| `name` | String | Game Title. |
| `creator` | String | Developer/Creator name. |
| `version` | String | Current version string (e.g., "v0.8.6 Public"). |
| `status` | String | "Completed", "Ongoing", "On Hold", "Abandoned", or "1" (F95Checker code). |
| `tracked` | Boolean | `true` if this game is being actively monitored for file updates. |
| `tags` | String | JSON-formatted string of relevant tags (e.g., `"[12, 45]"`). |
| `f95_last_update` | Timestamp | When the game was last updated on F95Zone (ISO 8601). |
| `cover_url` | String | URL to the game's banner/cover image (Local Cache). |
| `last_updated_at` | Timestamp | When this record was last updated in our local DB. |
| `last_enriched` | Timestamp | When rich details were last fetched from F95Checker. |
| `details_json` | JSON String | **Rich Parsed Metadata**. See [Details Dictionary](#details_json-dictionary) below. |

---

## 📖 `details_json` Data Dictionary

The `details_json` field contains specific, high-value data retrieved from F95Checker. It is stored as a JSON string and must be parsed.

### Core Fields
- **`description`**: HTML/Text summary of the game plot.
- **`changelog`**: Text history of recent updates.
- **`cover`**: URL to the game's banner/cover image.
- **`screens`**: Array of URLs for gameplay screenshots.
- **`tags`**: String representation of a list of Tag IDs (e.g., `"[12, 45, ...]"`). Use F95Zone tag IDs to map these.

### 📥 Downloads Structure (`downloads`)
The most complex and critical field. It is a nested list structure supporting multiple platforms and mirrors.

**Structure**:
```json
[
  [ "Platform Name", [ [ "Host Name", "Link or XPath" ], ... ] ],
  ...
]
```

**Example Data**:
```json
[
  [
    "Win/Linux", 
    [ 
      ["MEGA", "https://f95zone.to/masked/mega.nz/..."],
      ["GDRIVE", "https://f95zone.to/masked/drive.google.com/..."],
      ["VIKINGFILE", "//a[starts-with(@href,'https://vikingfile.com/')][1]"]
    ]
  ],
  [
    "Android", 
    [ ... ] 
  ]
]
```

**Handling Links**:
1.  **Direct URLs**: Most links (MEGA, GDrive, Pixeldrain) are provided as `https://f95zone.to/masked/...` URLs. These are safe to present to the user directly.
2.  **XPaths**: Some hosts (VikingFile, Buzzheavier) may return an **XPath Selector** string starting with `//a[...]`. 
    *   *Meaning*: The API could not resolve the direct link.
    *   *Action*: You must scraper logic to visit the thread and click the element matching this XPath, OR simply direct the user to the thread URL to download manually.

### 📊 Metrics
- **`rating`**: Float (0.00 - 5.00). User rating.
- **`views`**: Integer. Total thread views.
- **`likes`**: Integer. Total likes.
- **`reviews`**: Array of objects containing recent user reviews:
    - `user`: Name
    - `score`: int (1-5)
    - `message`: Review text
    - `timestamp`: Epoch time

### 🚩 Status Codes (`status`)
F95Checker uses integer codes for status.
| Code | Status | Description |
| :--- | :--- | :--- |
| `1` | **Normal/Ongoing** | In active development. |
| `2` | **Completed** | Story is finished. |
| `3` | **On Hold** | Development paused. |
| `4` | **Abandoned** | Development halted. |
| `5` | **Unchecked** | New/Unknown. |

### 🏷️ Top Tags (`tags`)
Tags are returned as a list of integers. Common mappings include:
| ID | Tag | ID | Tag |
| :--- | :--- | :--- | :--- |
| `1` | 2D Game | `2` | 2DCG |
| `3` | 3D Game | `4` | 3DCG |
| `5` | Adventure | `105` | RPG |
| `104` | Romance | `115` | Simulator |
| `60` | Graphic Violence | `57` | Futa/Trans |
| `136` | Virtual Reality | `56` | Furry |
| `41` | Character Creation | `137` | Voiced |
*(See `reference_lib/F95Checker-main/common/structs.py` for full 140+ tag list)*

### 🎮 Engine / Content Type (`type`)
The `type` field in `details_json` returns an integer code representing the game engine or content category.

| ID | Engine/Type | ID | Engine/Type |
| :--- | :--- | :--- | :--- |
| `1` | Misc | `15` | Request |
| `2` | ADRIFT | `16` | Tads |
| `3` | Cheat Mod | `17` | Tool |
| `4` | Flash | `18` | Tutorial |
| `5` | HTML | `19` | Unity |
| `6` | Java | `20` | Unreal Engine |
| `7` | Collection | `21` | WebGL |
| `8` | Mod | `22` | Wolf RPG |
| `9` | Others | `23` | Unchecked |
| `10` | QSP | `24` | Comics |
| `11` | RAGS | `25` | GIF |
| `12` | READ ME | `26` | Manga |
| `13` | RPGM | `27` | Pinup |
| `14` | Ren'Py | `28` | SiteRip |
|  |  | `29` | Video |
|  |  | `30` | CG |

*(Source: `reference_lib/F95Checker-main/common/structs.py`)*
