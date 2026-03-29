from pydantic import BaseModel, ConfigDict
from datetime import datetime
from typing import Optional

class BaseModelDB(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: Optional[int] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None