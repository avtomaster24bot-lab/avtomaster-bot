# test_subcategories.py
import asyncio
from database import db
from repositories.subcategory_repo import SubcategoryRepository

async def test():
    async with db.session() as conn:
        repo = SubcategoryRepository(conn)
        # укажи реальный category_id из базы, например 1
        subs = await repo.get_by_category_id(1)
        print(f"Найдено подуслуг: {len(subs)}")
        for s in subs[:5]:
            print(f"  {s.name} (id={s.id})")

if __name__ == "__main__":
    asyncio.run(test())