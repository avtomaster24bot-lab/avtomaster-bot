from repositories.station_repo import StationRepository
from models.station import Station

class StationService:
    def __init__(self, conn):
        self.station_repo = StationRepository(conn)

    async def get_station_by_admin(self, admin_id: int) -> Station | None:
        return await self.station_repo.get_by_admin_id(admin_id)