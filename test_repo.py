# test_repo.py
import asyncio
from database import db
from repositories.car_wash_repo import CarWashRepository

async def test():
    async with db.session() as conn:
        repo = CarWashRepository(conn)
        washes = await repo.get_by_city("Талдыкорган")
        print(f"Найдено моек: {len(washes)}")
        for w in washes:
            print(f"  {w.name} (id={w.id})")

if __name__ == "__main__":
    asyncio.run(test())