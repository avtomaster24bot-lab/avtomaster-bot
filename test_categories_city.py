import asyncio
from database import db
from repositories.category_repo import CategoryRepository

async def test():
    async with db.session() as conn:
        repo = CategoryRepository(conn)
        categories = await repo.get_by_city("Талдыкорган")
        print(f"Найдено категорий для Талдыкорган: {len(categories)}")
        for cat in categories[:5]:
            print(f"  {cat.name} (id={cat.id})")

if __name__ == "__main__":
    asyncio.run(test())