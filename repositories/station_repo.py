# repositories/station_repo.py
from .base import BaseRepository
from models.station import Station

class StationRepository(BaseRepository[Station]):
    async def get_by_id(self, station_id: int) -> Station | None:
        row = await self._fetch_one("SELECT * FROM stations WHERE id = ?", (station_id,))
        if not row:
            return None
        cursor = await self.conn.execute("PRAGMA table_info(stations)")
        columns = await cursor.fetchall()
        keys = [col[1] for col in columns]
        data = dict(zip(keys, row))
        return Station(**data)

    async def get_by_admin_id(self, admin_id: int) -> Station | None:
        row = await self._fetch_one("SELECT * FROM stations WHERE admin_id = ?", (admin_id,))
        if not row:
            return None
        cursor = await self.conn.execute("PRAGMA table_info(stations)")
        columns = await cursor.fetchall()
        keys = [col[1] for col in columns]
        data = dict(zip(keys, row))
        return Station(**data)

    async def get_by_category_and_city(self, category_id: int, city_name: str):
        query = """
            SELECT s.* FROM stations s
            JOIN station_categories sc ON s.id = sc.station_id
            JOIN cities c ON s.city_id = c.id
            WHERE sc.category_id = ? AND c.name = ?
            ORDER BY s.priority ASC, s.is_premium DESC
        """
        rows = await self._fetch_all(query, (category_id, city_name))
        if not rows:
            return []
        cursor = await self.conn.execute("PRAGMA table_info(stations)")
        columns = await cursor.fetchall()
        keys = [col[1] for col in columns]
        return [Station(**dict(zip(keys, row))) for row in rows]

    async def get_by_city(self, city_name: str):
        """Возвращает все СТО в городе."""
        query = """
            SELECT s.* FROM stations s
            JOIN cities ct ON s.city_id = ct.id
            WHERE ct.name = ?
        """
        rows = await self._fetch_all(query, (city_name,))
        if not rows:
            return []
        cursor = await self.conn.execute("PRAGMA table_info(stations)")
        columns = await cursor.fetchall()
        keys = [col[1] for col in columns]
        return [Station(**dict(zip(keys, row))) for row in rows]

    async def create(self, data: dict) -> int:
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        query = f"INSERT INTO stations ({columns}) VALUES ({placeholders})"
        cursor = await self._execute(query, tuple(data.values()))
        await self.conn.commit()
        return cursor.lastrowid