from typing import Optional
from .base import BaseModelDB

class Supplier(BaseModelDB):
    name: str
    type: str
    city_id: int
    admin_id: int
    phone: Optional[str] = None
    address: Optional[str] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    work_hours: Optional[str] = None
    delivery_available: bool = False
    rating: float = 0.0
    reviews_count: int = 0
    subscription_until: Optional[str] = None