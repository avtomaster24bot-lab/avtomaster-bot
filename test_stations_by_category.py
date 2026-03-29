# test_stations_by_category.py
import asyncio
from database import db
from repositories.station_repo import StationRepository

async def test():
    async with db.session() as conn:
        repo = StationRepository(conn)
        # Выбери любую категорию, которая есть в твоём городе, например id=1 (Ремонт двигателя)
        stations = await repo.get_by_category_and_city(1, "Талдыкорган")
        print(f"Найдено СТО для категории 1: {len(stations)}")
        for s in stations:
            print(f"  {s.name} (id={s.id})")

if __name__ == "__main__":
    asyncio.run(test())