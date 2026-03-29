from typing import Optional
from .base import BaseModelDB

class Station(BaseModelDB):
    name: str
    city_id: int
    admin_id: int
    phone: Optional[str] = None
    address: Optional[str] = None
    priority: int = 0
    is_premium: bool = False
    rating: float = 0.0
    reviews_count: int = 0
    subscription_until: Optional[str] = None
    work_hours: Optional[str] = None