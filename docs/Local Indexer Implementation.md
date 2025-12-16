# Local F95Zone Indexer Implementation Guide

This guide explains how to replicate the F95Checker "Indexer" logic to build your own local game database. This allows you to search and filter games instantaneously without spamming F95Zone with requests.

## 1. Architecture Overview

To replace the F95Checker API, you need three core components:

1.  **The Database**: To store game metadata (Title, Version, Status, Download Links).
2.  **The Scraper**: To parse F95Zone thread pages and extract data.
3.  **The Scheduler**: To periodically check for updates (the "Crawler").

```mermaid
graph TD
    User[User / UI] -->|Search (Instant)| DB[(Local Database)]
    Scheduler -->|1. Check for Updates| F95[F95Zone.to]
    Scheduler -->|2. Scrape New Data| Scraper
    Scraper -->|3. Update/Insert| DB
```

## 2. The Database Schema

Since you want to store this locally, **SQLite** is the best choice (lightweight, single file). If you are using Python, use **SQLAlchemy** or **Tortoise-ORM**.

### Recommended Schema (SQLAlchemy)

```python
from datetime import datetime
from sqlalchemy import create_engine, Column, Integer, String, Text, Float, DateTime, ForeignKey, JSON
from sqlalchemy.orm import declarative_base, relationship

Base = declarative_base()

class Game(Base):
    __tablename__ = 'games'
    
    id = Column(Integer, primary_key=True)  # This should be the F95Zone Thread ID
    title = Column(String, index=True)
    version = Column(String)
    developer = Column(String, index=True)
    status = Column(String)  # 'Completed', 'Ongoing', 'Abandoned'
    tags = Column(JSON)      # Store as list of strings
    
    # Metadata
    description = Column(Text)
    cover_url = Column(String)
    last_checked_at = Column(DateTime, default=datetime.utcnow)
    last_update_date = Column(DateTime) # The 'Thread Updated' date from F95
    
    downloads = relationship("Download", back_populates="game", cascade="all, delete-orphan")

class Download(Base):
    __tablename__ = 'downloads'
    
    id = Column(Integer, primary_key=True)
    game_id = Column(Integer, ForeignKey('games.id'))
    label = Column(String)  # e.g., "Win/Linux", "Mega"
    url = Column(String)    # The URL or XPath expression
    
    game = relationship("Game", back_populates="downloads")
```

## 3. The Scraper Logic

The core complexity is parsing the "Thread Starter Post" on F95Zone.

**Libraries needed:**
*   `BeautifulSoup4` and `lxml` (for parsing HTML)
*   `aiohttp` (for async requests) or `requests` (for blocking)

### 3.1 Fetching headers
You must inspect the first post (`.message-threadStarterPost`). F95Checker uses regex to find lines starting with specific keys within the post text.

**Key attributes to parse:**
*   **Version**: Look for `^Version: (.*)` (case insensitive).
*   **Developer**: Look for `^Developer: (.*)` or `^Artist: (.*)`.
*   **Status**: Infer from tags (e.g., "[Completed]", "[Abandoned]") or thread prefixes.

### 3.2 Extracting Download Links
This is the hardest part. The text is often unstructured.

**Strategy:**
1.  Locate the "Downloads" text node in the post.
2.  Iterate through subsequent elements.
3.  Capture `<a>` tags.
4.  **Important**: Store the direct `href` if it's an external host (Mega, Mediafire, Gdrive).
5.  **Bypassing "Link Protection"**:
    *   F95Zone sometimes wraps links or hides them.
    *   If you can't find the direct link in the HTML source (e.g., it's injected by JS), you might need to use **Playwright** to render the page, OR store an **XPath** to click it later (like F95Checker does).
    *   *Simpler Approach*: Just extract every `a.link` inside the `block-body` of the starter post that matches known file hosts.

## 4. The Scheduler (Update Loop)

You don't want to rescrape 5000 games every hour. You need an efficient check strategy.

### Step 1: The "Lite" Check (Version Comparison)
F95Zone listing pages (e.g., `/forums/games.2/?order=last_post_date`) contain the **Thread ID**, **Title**, **Prefixes** (Status), and **Version** (often in the title like `[v1.0]`).

1.  Scrape the listing pages (Pages 1-5 covers most recent updates).
2.  For each thread found:
    *   Compare the version/date in the listing with your DB.
    *   **If different**: Mark for "Full Scrape".
    *   **If same**: Skip.

### Step 2: The "Full" Scrape
For games marked for update:
1.  Fetch `https://f95zone.to/threads/{id}/`.
2.  Run the **Scraper Logic** (Section 3).
3.  Update the `Game` record in your DB.
4.  Download the new cover image if changed.

## 5. Implementing Search

Once data is in SQLite, you can perform instant searches:

```python
def search_games(query: str, db_session):
    # Case-insensitive SQL LIKE search
    return db_session.query(Game).filter(
        (Game.title.ilike(f'%{query}%')) | 
        (Game.developer.ilike(f'%{query}%')) |
        (Game.tags.cast(String).ilike(f'%{query}%'))
    ).all()
```

## 6. Avoiding Bans (Rate Limiting)

*   **Cookies**: You **MUST** log in. Export your F95Zone cookies (specifically `xf_user`, `xf_session`) and send them with every request.
*   **Rate Limit**: Limit requests to ~1 per 2 seconds. F95Checker uses a generic `AsyncLimiter`.
*   **User Agent**: Use a real browser User-Agent string.

## Checklist for Implementation

- [ ] Set up `uv` project with `fastapi`, `sqlalchemy`, `beautifulsoup4`, `aiohttp`.
- [ ] Create `models.py` with the database schema.
- [ ] Write `scraper.py` to parse a single thread HTML file.
- [ ] Write `crawler.py` to iterate through thread IDs or listing pages.
- [ ] Create a simple API/UI to query your local database.
