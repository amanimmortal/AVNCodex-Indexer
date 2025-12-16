# F95Checker API Integration Guide

This guide documents how to integrate with the F95Checker API (`https://api.f95checker.dev`) to retrieve game updates and metadata without scraping F95Zone directly for every request.

> [!IMPORTANT]
> This API is a cache service maintained by the F95Checker project. Usage should be respectful of their resources.

## 1. API Overview

*   **Base URL**: `https://api.f95checker.dev`
*   **Protocol**: HTTPS
*   **Authentication**: None required (Public).
*   **User-Agent**: Recommended to set a descriptive User-Agent (e.g., `YourApp/1.0`).

## 2. Endpoints

### 2.1. Fast Check (Bulk Updates)
Used to quickly check if games have been updated.

*   **GET** `/fast?ids={id1},{id2},...`
*   **Parameters**:
    *   `ids`: Comma-separated list of F95Zone Thread IDs (integers).
    *   *Limit*: The official client batches requests in groups of **10 IDs**.
*   **Response**: JSON Dictionary mapping `ThreadID` -> `LastChangedTimestamp` (int).

**Example Request:**
```http
GET https://api.f95checker.dev/fast?ids=12345,67890
```

**Example Response:**
```json
{
  "12345": 1634567890,
  "67890": 1634567999
}
```

### 2.2. Full Check (Game Details)
Retrieves detailed metadata for a specific game, including version, status, tags, and downloads.

*   **GET** `/full/{thread_id}?ts={timestamp}`
*   **Parameters**:
    *   `thread_id`: The F95Zone Thread ID.
    *   `ts`: The `LastChangedTimestamp` value returned from the `/fast` endpoint. This ensures you are fetching the version of the cache you expect.
*   **Response**: JSON Object containing full game details.

**Key Response Fields:**
*   `name`: Game Title
*   `version`: Current Version String
*   `status`: Game Status ID (see enum below)
*   `tags`: List of tags
*   `downloads`: List of download groups.

## 3. Handling Download Links (The XPath Mechanism)

To prevent abuse and link rot, the API often does **not** return direct URLs for external file hosts (Mega, Mediafire, etc.). Instead, it returns an **XPath expression**.

### How to detect:
1.  **Direct Links**: If the URL is a valid http/https link to a supported host (or F95 attachment), use it directly.
2.  **XPath Expressions**: If the "URL" looks like `//a[starts-with(@href,'https://mega.nz/')]`, it is an XPath expression.

### How to resolve XPaths:
You must perform a request to the actual F95Zone thread page and evaluate the XPath against the HTML.

**Python Example (using `lxml`):**
```python
from lxml import html
import requests

def resolve_download_link(thread_url, xpath_expr):
    # 1. Fetch the actual thread page (requires login cookies usually)
    response = requests.get(thread_url, cookies=my_cookies)
    tree = html.fromstring(response.content)
    
    # 2. Evaluate XPath
    # Note: The API sends 1-indexed XPath snapshot items sometimes, 
    # you might need to adjust logic if it uses [N] syntax.
    results = tree.xpath(xpath_expr)
    
    if results:
        # Return the href of the found element
        return results[0].get('href')
    return None
```

## 4. Helper Enums

### Game Status
The `status` field in the JSON response maps to these integers:
*   `0`: Normal / Ongoing
*   `1`: Completed
*   `2`: On Hold
*   `3`: Abandoned

## 5. Recommended Workflow

1.  **Fast Check**: Store your local `LastChangedTimestamp` for each game. Periodically call `/fast` with your game IDs.
2.  **Compare**: If the API returns a higher timestamp than your local one, the game is updated.
3.  **Full Check**: Call `/full/{id}` for the updated games to get the new version string and metadata.
4.  **Download**: If the user wants to update, check the `downloads` list.
    *   If it's a direct link, download it.
    *   If it's an XPath, fetch the thread page and resolve it.
