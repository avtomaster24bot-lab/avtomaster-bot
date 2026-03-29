# repositories/car_wash_repo.py
from .base import BaseRepository
from models.car_wash import CarWash

class CarWashRepository(BaseRepository[CarWash]):
    async def get_by_id(self, wash_id: int) -> CarWash | None:
        row = await self._fetch_one("SELECT * FROM car_washes WHERE id = ?", (wash_id,))
        if not row:
            return None
        cursor = await self.conn.execute("PRAGMA table_info(car_washes)")
        columns = await cursor.fetchall()
        keys = [col[1] for col in columns]
        data = dict(zip(keys, row))
        return CarWash(**data)

    async def get_by_admin_id(self, admin_id: int) -> CarWash | None:
        row = await self._fetch_one("SELECT * FROM car_washes WHERE admin_id = ?", (admin_id,))
        if not row:
            return None
        cursor = await self.conn.execute("PRAGMA table_info(car_washes)")
        columns = await cursor.fetchall()
        keys = [col[1] for col in columns]
        data = dict(zip(keys, row))
        return CarWash(**data)

    async def get_by_city(self, city_name: str):
        query = """
            SELECT cw.* FROM car_washes cw
            JOIN cities ct ON cw.city_id = ct.id
            WHERE ct.name = ?
        """
        rows = await self._fetch_all(query, (city_name,))
        if not rows:
            return []
        cursor = await self.conn.execute("PRAGMA table_info(car_washes)")
        columns = await cursor.fetchall()
        keys = [col[1] for col in columns]
        return [CarWash(**dict(zip(keys, row))) for row in rows]

    async def create(self, data: dict) -> int:
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        query = f"INSERT INTO car_washes ({columns}) VALUES ({placeholders})"
        cursor = await self._execute(query, tuple(data.values()))
        await self.conn.commit()
        return cursor.lastrowid