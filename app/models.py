from sqlmodel import SQLModel, Field
from typing import Optional
from datetime import datetime


class Game(SQLModel, table=True):
    __tablename__ = "games"

    id: int = Field(primary_key=True)  # F95 Thread ID
    name: str = Field(index=True)
    version: Optional[str] = None
    status: Optional[str] = None  # Completed, Ongoing, etc.
    author: Optional[str] = None
    tracked: bool = Field(default=False)

    last_updated_at: datetime = Field(default_factory=datetime.utcnow)
    f95_last_update: Optional[datetime] = None

    details_json: Optional[str] = None
