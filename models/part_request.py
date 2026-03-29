from typing import Optional
from .base import BaseModelDB

class PartRequest(BaseModelDB):
    user_id: int
    city: str
    part_name: str
    car_info: Optional[str] = None
    comment: Optional[str] = None
    photo: Optional[str] = None
    status: str = "new"
    accepted_by: Optional[int] = None
    accepted_at: Optional[str] = None
    client_chat_id: Optional[int] = None
    client_message_id: Optional[int] = None