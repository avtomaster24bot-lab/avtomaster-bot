from typing import Optional
from .base import BaseModelDB

class CarWash(BaseModelDB):
    name: str
    city_id: int
    admin_id: int
    phone: Optional[str] = None
    address: Optional[str] = None
    boxes: int = 1
    duration: int = 30
    working_hours: Optional[str] = None
    rating: float = 0.0
    reviews_count: int = 0
    slot_duration: int = 30
    break_duration: int = 5
    work_start: str = "09:00"
    work_end: str = "21:00"
    days_off: Optional[str] = None  # JSON
    subscription_until: Optional[str] = None