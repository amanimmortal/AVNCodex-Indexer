# AVNCodex Indexer Test Commands

Here are some `curl` commands to test the API endpoints.
Ref: `app/routers/games.py`

## Base URL
`http://localhost:8000`

## 1. Check API Status
Verify the service is running.

```bash
curl -X GET http://localhost:8000/
```

## 2. Search Games
### Basic Search
Search for games matching a query string.

```bash
curl -X GET "http://localhost:8000/games/search?q=summertime"
```

### Advanced Search
Search with status and tags.
*   `status`: e.g., "ongoing", "completed" (depending on your data model strings)
*   `tags`: Can be repeated.

```bash
curl -X GET "http://localhost:8000/games/search?q=rpg&status=ongoing&tags=3d&tags=fantasy"
```

## 3. Get Game Details
Fetch details for a specific game by its ID (F95Zone ID).
Replace `12345` with a valid Game ID.

```bash
curl -X GET http://localhost:8000/games/12345
```

## 4. Game Management Operations
### Track a Game
Start tracking a game (this syncs details immediately).

```bash
curl -X POST http://localhost:8000/games/12345/track
```

### Refresh Game Data
Force a refresh of the game data from the source.

```bash
curl -X POST http://localhost:8000/games/12345/refresh
```

### Untrack a Game
Stop tracking a game.

```bash
curl -X POST http://localhost:8000/games/12345/untrack
```

## 5. System Operations
### Manual Update Trigger
Trigger the background daily update task manually.

```bash
curl -X POST http://localhost:8000/games/trigger-update
```
