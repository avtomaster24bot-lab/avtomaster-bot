import aiosqlite
from typing import TypeVar, Generic, List, Optional, Dict, Any

T = TypeVar("T")

class BaseRepository(Generic[T]):
    def __init__(self, conn: aiosqlite.Connection):
        self.conn = conn

    async def _execute(self, query: str, params: tuple = ()) -> aiosqlite.Cursor:
        return await self.conn.execute(query, params)

    async def _fetch_one(self, query: str, params: tuple = ()) -> Optional[tuple]:
        cursor = await self._execute(query, params)
        return await cursor.fetchone()

    async def _fetch_all(self, query: str, params: tuple = ()) -> List[tuple]:
        cursor = await self._execute(query, params)
        return await cursor.fetchall()