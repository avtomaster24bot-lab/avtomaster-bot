# repositories/part_request_repo.py
from .base import BaseRepository
from models.part_request import PartRequest

class PartRequestRepository(BaseRepository[PartRequest]):
    async def create(self, data: dict) -> int:
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        query = f"INSERT INTO part_requests ({columns}) VALUES ({placeholders})"
        cursor = await self._execute(query, tuple(data.values()))
        await self.conn.commit()
        return cursor.lastrowid

    async def update(self, request_id: int, data: dict) -> None:
        set_clause = ", ".join([f"{k} = ?" for k in data.keys()])
        query = f"UPDATE part_requests SET {set_clause} WHERE id = ?"
        await self._execute(query, tuple(data.values()) + (request_id,))
        await self.conn.commit()

    async def get_by_id(self, request_id: int) -> PartRequest | None:
        row = await self._fetch_one("SELECT * FROM part_requests WHERE id = ?", (request_id,))
        if not row:
            return None
        keys = [d[0] for d in (await self.conn.execute("PRAGMA table_info(part_requests)")).fetchall()]
        data = dict(zip(keys, row))
        return PartRequest(**data)

    async def get_by_city(self, city: str, status: str = 'new'):
        rows = await self._fetch_all(
            "SELECT * FROM part_requests WHERE city = ? AND status = ? ORDER BY created_at DESC",
            (city, status)
        )
        keys = [d[0] for d in (await self.conn.execute("PRAGMA table_info(part_requests)")).fetchall()]
        return [PartRequest(**dict(zip(keys, row))) for row in rows]

    async def get_by_user(self, user_id: int, limit: int = 20):
        rows = await self._fetch_all(
            "SELECT * FROM part_requests WHERE user_id = ? ORDER BY created_at DESC LIMIT ?",
            (user_id, limit)
        )
        keys = [d[0] for d in (await self.conn.execute("PRAGMA table_info(part_requests)")).fetchall()]
        return [PartRequest(**dict(zip(keys, row))) for row in rows]