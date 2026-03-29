from .base import BaseRepository
from models.category import Category

class CategoryRepository(BaseRepository[Category]):
    async def get_by_id(self, category_id: int) -> Category | None:
        row = await self._fetch_one("SELECT * FROM categories WHERE id = ?", (category_id,))
        if not row:
            return None
        return Category(id=row[0], name=row[1], city_id=row[2])

    async def get_by_city(self, city_name: str):
        query = """
            SELECT c.* FROM categories c
            JOIN cities ct ON c.city_id = ct.id
            WHERE ct.name = ?
        """
        rows = await self._fetch_all(query, (city_name,))
        return [Category(id=r[0], name=r[1], city_id=r[2]) for r in rows]