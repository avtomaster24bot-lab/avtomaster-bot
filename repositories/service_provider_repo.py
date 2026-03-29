from .base import BaseRepository
from models.service_provider import ServiceProvider

class ServiceProviderRepository(BaseRepository[ServiceProvider]):
    async def get_by_id(self, provider_id: int) -> ServiceProvider | None:
        row = await self._fetch_one("SELECT * FROM service_providers WHERE id = ?", (provider_id,))
        if not row:
            return None
        cursor = await self.conn.execute("PRAGMA table_info(service_providers)")
        columns = await cursor.fetchall()
        keys = [col[1] for col in columns]
        data = dict(zip(keys, row))
        return ServiceProvider(**data)

    async def get_by_admin_id(self, admin_id: int) -> ServiceProvider | None:
        row = await self._fetch_one("SELECT * FROM service_providers WHERE admin_id = ?", (admin_id,))
        if not row:
            return None
        cursor = await self.conn.execute("PRAGMA table_info(service_providers)")
        columns = await cursor.fetchall()
        keys = [col[1] for col in columns]
        data = dict(zip(keys, row))
        return ServiceProvider(**data)

    async def get_by_city_and_type(self, city_name: str, service_type: str):
        query = """
            SELECT sp.* FROM service_providers sp
            JOIN cities ct ON sp.city_id = ct.id
            WHERE ct.name = ? AND sp.service_type = ?
        """
        rows = await self._fetch_all(query, (city_name, service_type))
        if not rows:
            return []
        cursor = await self.conn.execute("PRAGMA table_info(service_providers)")
        columns = await cursor.fetchall()
        keys = [col[1] for col in columns]
        return [ServiceProvider(**dict(zip(keys, row))) for row in rows]

    async def get_by_city(self, city_name: str):
        query = """
            SELECT sp.* FROM service_providers sp
            JOIN cities ct ON sp.city_id = ct.id
            WHERE ct.name = ?
        """
        rows = await self._fetch_all(query, (city_name,))
        if not rows:
            return []
        cursor = await self.conn.execute("PRAGMA table_info(service_providers)")
        columns = await cursor.fetchall()
        keys = [col[1] for col in columns]
        return [ServiceProvider(**dict(zip(keys, row))) for row in rows]