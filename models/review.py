from typing import Optional
from .base import BaseModelDB

class Review(BaseModelDB):
    user_id: int
    entity_type: str
    entity_id: int
    rating: int
    comment: Optional[str] = None
    moderated: bool = False
    hidden: bool = False