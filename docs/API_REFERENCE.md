# AVNCodex Indexer API Reference

This document provides instructions for developers interacting with the AVNCodex Indexer API. It covers setup, endpoints, and a detailed dictionary of the data structures returned.

## 🚀 Getting Started

### Base URL
The API runs on port `5005` by default.
- **Base URL**: `http://192.168.200.16:5005`
- **Swagger UI** (Interactive Docs): `http://192.168.200.16:5005/docs`
- **ReDoc**: `http://192.168.200.16:5005/redoc`

### Authentication
Currently, the API is **public** and does not require authentication. Ensure it is not exposed to the open internet without a reverse proxy or firewall.

---

## 📡 Endpoints

### 1. Search Games
Search for a game by name. This performs a hybrid search (Local DB -> F95Zone Direct API -> RSS -> F95Checker).
- **Method**: `GET`
- **Endpoint**: `/games/search`
- **Params**: 
    - `q` (string, required): The search query (e.g., "Eternum").
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

### 4. Force Refresh
Manually force a sync for a specific game from upstream sources.
- **Method**: `POST`
- **Endpoint**: `/games/{game_id}/refresh`

### 5. Trigger Global Update
Manually trigger the scheduled task that checks for all updates.
- **Method**: `POST`
- **Endpoint**: `/games/trigger-update`

---

## 💾 Data Models

### Game Object Model
The core response object representing a game.

| Field | Type | Description |
| :--- | :--- | :--- |
| `id` | Integer | The F95Zone Thread ID (Unique Identifier). |
| `name` | String | Game Title. |
| `author` | String | Developer/Creator name. |
| `version` | String | Current version string (e.g., "v0.8.6 Public"). |
| `status` | String | "Completed", "Ongoing", "On Hold", "Abandoned", or "1" (F95Checker code). |
| `tracked` | Boolean | `true` if this game is being actively monitored for file updates. |
| `f95_last_update` | Timestamp | When the game was last updated on F95Zone (ISO 8601). |
| `last_updated_at` | Timestamp | When this record was last updated in our local DB. |
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

### 🚩 Status Codes
If `status` is returned as a code/string from F95Checker:
- **`1`**: Ongoing / In Development.
- **Completed**: Story is finished.
- **Abandoned**: Development halted.
- **On Hold**: Development paused.
