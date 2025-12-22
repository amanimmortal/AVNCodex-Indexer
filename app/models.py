from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime, timezone


class Game(SQLModel, table=True):
    __tablename__ = "games"

    # Primary Key is the F95 Thread ID
    f95_id: int = Field(primary_key=True)

    # Basic Info (F95Zone)
    name: str = Field(index=True)
    creator: Optional[str] = None
    version: Optional[str] = None
    cover_url: Optional[str] = None
    f95_last_update: Optional[datetime] = None

    # Tracked Status (Internal)
    tracked: bool = Field(default=False)

    # Rich Details (F95Checker ONLY)
    tags: Optional[str] = None  # JSON List[str]
    status: Optional[str] = None
    type_id: Optional[int] = Field(default=None, index=True)
    status_id: Optional[int] = Field(default=None, index=True)
    details_json: Optional[str] = None
    last_enriched: Optional[datetime] = None

    # Internal Timestamps
    last_updated_at: datetime = Field(
        default_factory=lambda: datetime.now(timezone.utc)
    )

    @property
    def id(self) -> int:
        return self.f95_id

    @id.setter
    def id(self, value: int):
        self.f95_id = value
