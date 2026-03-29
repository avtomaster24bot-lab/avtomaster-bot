from typing import Optional
from .base import BaseModelDB

class Category(BaseModelDB):
    name: str
    city_id: int