from typing import Optional
from .base import BaseModelDB

class TowTruck(BaseModelDB):
    name: str
    city_id: int
    admin_id: int
    phone: Optional[str] = None
    address: Optional[str] = None
    rating: float = 0.0
    reviews_count: int = 0
    subscription_until: Optional[str] = None