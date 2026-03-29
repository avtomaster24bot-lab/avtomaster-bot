from typing import Optional
from .base import BaseModelDB

class Subcategory(BaseModelDB):
    name: str
    category_id: int