# API Integration Plan: F95Zone `latest_data.php`

This plan outlines the integration of the discovered F95Zone API into the `AVNCodex` scraper. This API provides a more robust, efficient, and data-rich alternative to HTML scraping.

## 1. API Overview

- **Endpoint:** `https://f95zone.to/sam/latest_alpha/latest_data.php`
- **Method:** `GET`
- **Response Format:** JSON
- **Auth:** Standard session cookies are required (Cloudflare protection + F95Zone login). Use existing `requests` session.

## 2. API Parameters (`cmd=list`)

The primary command for game data is `list`.

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `cmd` | `string` | **Required** | Must be set to `list`. |
| `cat` | `string` | `games` | Category. Options: `games`, `mods`, `assets`, `comics`. |
| `page` | `int` | `1` | Pagination page number. |
| `rows` | `int` | `90` | Number of items per page. (Recommended: 60-90) |
| `sort` | `string` | `date` | Sort order. Options: `date`, `likes`, `views`, `rating`, `title`. |
| `search` | `string` | `null` | **Game Title Search**. URL encoded string. |
| `tags[]` | `array` | `[]` | **Tag ID filtering**. Example: `tags[]=2209`. Logical operator is AND (default). |
| `notags[]`| `array` | `[]` | Exclude games with these Tag IDs. |
| `tagtype` | `string` | `and` | Logic for multiple tags: `and` (match all) or `or` (match any). |
| `prefixes[]`| `array` | `[]` | Filter by Prefix IDs (e.g., Status, Engine). |
| `noprefixes[]`| `array`| `[]` | Exclude Prefix IDs. |
| `date` | `int` | `0` | Filter by days since update (e.g., `365`). |
| `_` | `int` | `timestamp` | Cache buster (current timestamp). |

## 3. Search & Filtering Logic

### 3.1 Game Title Search
To search for a specific game by name (e.g., "Eternum"):
```http
GET ...?cmd=list&cat=games&search=eternum
```

### 3.2 Tag Filtering
To search for games with specific tags (e.g., Tag ID `2209`):
```http
GET ...?cmd=list&cat=games&tags[]=2209
```
*Note: You can combine `search` and `tags[]` to refine results.*

### 3.3 Advanced Filtering (RSS-like)
The user provided example matches the valid API parameters:
```http
...?cmd=list&cat=games&prefixes[]=7&tags[]=2209&search=eternum&rows=60
```
This allows precise filtering identical to the RSS feed logic but with structured JSON output.

## 4. Response Schema

The API returns a JSON object. Key data is located in `msg.data`.

```json
{
  "status": "ok",
  "msg": {
    "data": [
      {
        "thread_id": 12345,             // Unique ID
        "title": "Game Title",          // Game Name
        "version": "v1.0",              // Current Version
        "creator": "Developer Name",    // Author
        "date": "2024-05-20",           // Last Update Date (YYYY-MM-DD or relative)
        "tags": ["Tag1", "Tag2"],       // Array of tag names or IDs
        "prefixes": ["Prefix1"],        // Array of prefix names/IDs
        "cover": "https://...",         // URL to cover image
        "rating": 4.5,                  // User rating
        "likes": 1500,                  // Like count
        "views": 50000,                 // View count
        "watched": false,               // User specific: watched status
        "new": false                    // Is new since last visit
      }
    ],
    "pagination": {
      "page": 1,
      "total": 10,
      "perPage": 90
    }
  }
}
```

## 5. Implementation Strategy

### 5.1 Python Implementation (`scraper.py`)

We will create a helper function `fetch_games_api` to handle the request construction.

```python
def fetch_games_api(
    session, 
    search: str = None, 
    tags: list[int] = None, 
    page: int = 1, 
    rows: int = 60
) -> dict:
    base_url = "https://f95zone.to/sam/latest_alpha/latest_data.php"
    
    params = {
        "cmd": "list",
        "cat": "games",
        "page": page,
        "rows": rows,
        "sort": "date"
    }

    if search:
        params["search"] = search
    
    if tags:
        # requests handles list conversion to tags[]=...
        params["tags[]"] = tags

    try:
        response = session.get(base_url, params=params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        print(f"API Request Failed: {e}")
        return None
```

### 5.2 Integration Steps

1.  **Replace RSS Logic**: The current RSS feed parsing logic can be replaced or augmented with this API.
2.  **Pagination Loop**: Implement a loop that checks `msg.pagination.page < msg.pagination.total` to fetch all results if necessary.
3.  **Data Mapping**: Map the JSON `thread_id`, `title`, and `version` to the existing internal `Game` model.
    *   *Benefit*: Access to `thread_id` allows direct link construction (`https://f95zone.to/threads/{thread_id}/`) without regex parsing metadata.

## 6. Verification
- Use `test_f95_api_search.py` (to be created) to verify that queries return expected results (e.g., searching for a known game returns 1+ result).
