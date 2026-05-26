from pydantic import BaseModel, Field
from typing import Optional
from datetime import date, time


class ChatRequest(BaseModel):
    restaurant_slug: str
    session_id: str
    message: str
    language: str = "de"


class ChatResponse(BaseModel):
    reply: str
    action: Optional[str] = None  # "reservation_created", "menu_shown", etc.
    data: Optional[dict] = None   # structured payload if needed


class ReservationRequest(BaseModel):
    guest_name: str
    guest_phone: Optional[str] = None
    guest_email: Optional[str] = None
    party_size: int = Field(ge=1, le=20)
    date: date
    time: time
    notes: Optional[str] = None


class MenuFilterRequest(BaseModel):
    category: Optional[str] = None
    exclude_allergens: list[str] = []
    tags: list[str] = []
    query: Optional[str] = None
