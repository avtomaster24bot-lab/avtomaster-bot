from typing import Optional, List, Any
from .base import BaseModelDB

class Request(BaseModelDB):
    user_id: int
    type: str
    category_id: Optional[int] = None
    subcategories: Optional[List[int]] = None  # JSON
    description: Optional[str] = None
    photo: Optional[str] = None
    city: Optional[str] = None
    status: str = "new"
    accepted_by: Optional[int] = None
    accepted_at: Optional[str] = None
    completed_at: Optional[str] = None
    total_amount: Optional[int] = None
    commission: Optional[int] = None
    service_subtype: Optional[str] = None
    client_chat_id: Optional[int] = None
    client_message_id: Optional[int] = None