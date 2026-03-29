# repositories/tow_truck_repo.py
from .base import BaseRepository
from models.tow_truck import TowTruck

class TowTruckRepository(BaseRepository[TowTruck]):
    async def get_by_id(self, tow_id: int) -> TowTruck | None:
        row = await self._fetch_one("SELECT * FROM tow_trucks WHERE id = ?", (tow_id,))
        if not row:
            return None
        cursor = await self.conn.execute("PRAGMA table_info(tow_trucks)")
        columns = await cursor.fetchall()
        keys = [col[1] for col in columns]
        data = dict(zip(keys, row))
        return TowTruck(**data)

    async def get_by_admin_id(self, admin_id: int) -> TowTruck | None:
        row = await self._fetch_one("SELECT * FROM tow_trucks WHERE admin_id = ?", (admin_id,))
        if not row:
            return None
        cursor = await self.conn.execute("PRAGMA table_info(tow_trucks)")
        columns = await cursor.fetchall()
        keys = [col[1] for col in columns]
        data = dict(zip(keys, row))
        return TowTruck(**data)

    async def get_by_city(self, city_name: str):
        query = """
            SELECT tt.* FROM tow_trucks tt
            JOIN cities ct ON tt.city_id = ct.id
            WHERE ct.name = ?
        """
        rows = await self._fetch_all(query, (city_name,))
        if not rows:
            return []
        cursor = await self.conn.execute("PRAGMA table_info(tow_trucks)")
        columns = await cursor.fetchall()
        keys = [col[1] for col in columns]
        return [TowTruck(**dict(zip(keys, row))) for row in rows]

    async def create(self, data: dict) -> int:
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        query = f"INSERT INTO tow_trucks ({columns}) VALUES ({placeholders})"
        cursor = await self._execute(query, tuple(data.values()))
        await self.conn.commit()
        return cursor.lastrowid