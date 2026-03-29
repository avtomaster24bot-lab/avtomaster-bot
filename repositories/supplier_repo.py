# repositories/supplier_repo.py
from .base import BaseRepository
from models.supplier import Supplier

class SupplierRepository(BaseRepository[Supplier]):
    async def get_by_id(self, supplier_id: int) -> Supplier | None:
        row = await self._fetch_one("SELECT * FROM suppliers WHERE id = ?", (supplier_id,))
        if not row:
            return None
        cursor = await self.conn.execute("PRAGMA table_info(suppliers)")
        columns = await cursor.fetchall()
        keys = [col[1] for col in columns]
        data = dict(zip(keys, row))
        return Supplier(**data)

    async def get_by_admin_id(self, admin_id: int) -> Supplier | None:
        row = await self._fetch_one("SELECT * FROM suppliers WHERE admin_id = ?", (admin_id,))
        if not row:
            return None
        cursor = await self.conn.execute("PRAGMA table_info(suppliers)")
        columns = await cursor.fetchall()
        keys = [col[1] for col in columns]
        data = dict(zip(keys, row))
        return Supplier(**data)

    async def get_by_city(self, city_name: str):
        query = """
            SELECT s.* FROM suppliers s
            JOIN cities ct ON s.city_id = ct.id
            WHERE ct.name = ?
        """
        rows = await self._fetch_all(query, (city_name,))
        if not rows:
            return []
        cursor = await self.conn.execute("PRAGMA table_info(suppliers)")
        columns = await cursor.fetchall()
        keys = [col[1] for col in columns]
        return [Supplier(**dict(zip(keys, row))) for row in rows]

    async def create(self, data: dict) -> int:
        columns = ", ".join(data.keys())
        placeholders = ", ".join(["?"] * len(data))
        query = f"INSERT INTO suppliers ({columns}) VALUES ({placeholders})"
        cursor = await self._execute(query, tuple(data.values()))
        await self.conn.commit()
        return cursor.lastrowid