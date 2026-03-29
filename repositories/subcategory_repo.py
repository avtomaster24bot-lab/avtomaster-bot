from .base import BaseRepository
from models.subcategory import Subcategory

class SubcategoryRepository(BaseRepository[Subcategory]):
    async def get_by_category_id(self, category_id: int):
        rows = await self._fetch_all("SELECT id, name, category_id FROM subcategories WHERE category_id = ?", (category_id,))
        return [Subcategory(id=r[0], name=r[1], category_id=r[2]) for r in rows]

    async def get_by_ids(self, ids: list):
        placeholders = ",".join("?" * len(ids))
        rows = await self._fetch_all(f"SELECT id, name, category_id FROM subcategories WHERE id IN ({placeholders})", ids)
        return [Subcategory(id=r[0], name=r[1], category_id=r[2]) for r in rows]