from typing import Optional
from .base import BaseModelDB

class User(BaseModelDB):
    telegram_id: int
    city: Optional[str] = None
    role: str = "client"
    full_name: Optional[str] = None
    phone: Optional[str] = None
    display_name_choice: str = "real_name"