# test_categories.py
import asyncio
from database import db
from repositories.category_repo import CategoryRepository

async def test():
    async with db.session() as conn:
        repo = CategoryRepository(conn)
        cats = await repo.get_by_city("Талдыкорган")
        print(f"Найдено категорий: {len(cats)}")
        for c in cats[:5]:
            print(f"  {c.name} (id={c.id})")

if __name__ == "__main__":
    asyncio.run(test())