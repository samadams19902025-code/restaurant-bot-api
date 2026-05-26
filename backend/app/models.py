"""
Multi-tenant models. Every table scoped to a restaurant via restaurant_id FK.
"""
import uuid
from datetime import datetime, date, time
from sqlalchemy import (
    Column, String, Text, Integer, Float, Boolean, Date, Time,
    DateTime, ForeignKey, JSON, UniqueConstraint
)
from sqlalchemy.orm import relationship
from app.db import Base


def gen_uuid():
    return str(uuid.uuid4())


# ── Restaurant (tenant) ──────────────────────────────────────────────

class Restaurant(Base):
    __tablename__ = "restaurants"

    id = Column(String, primary_key=True, default=gen_uuid)
    slug = Column(String(100), unique=True, nullable=False, index=True)  # "donna-leipzig"
    name = Column(String(200), nullable=False)
    address = Column(Text)
    phone = Column(String(50))
    website = Column(String(300))
    languages = Column(JSON, default=["de", "en", "it"])  # supported languages
    timezone = Column(String(50), default="Europe/Berlin")
    system_prompt = Column(Text)  # custom LLM personality/rules
    opening_hours = Column(JSON)  # {"mon": {"open": "11:00", "close": "22:00"}, ...}
    config = Column(JSON, default={})  # extra settings (max_party_size, etc.)
    created_at = Column(DateTime, default=datetime.utcnow)

    menu_items = relationship("MenuItem", back_populates="restaurant", cascade="all,delete")
    tables = relationship("Table", back_populates="restaurant", cascade="all,delete")
    reservations = relationship("Reservation", back_populates="restaurant", cascade="all,delete")
    faqs = relationship("FAQ", back_populates="restaurant", cascade="all,delete")
    reviews = relationship("Review", back_populates="restaurant", cascade="all,delete")
    conversations = relationship("Conversation", back_populates="restaurant", cascade="all,delete")


# ── Menu ──────────────────────────────────────────────────────────────

class MenuItem(Base):
    __tablename__ = "menu_items"

    id = Column(String, primary_key=True, default=gen_uuid)
    restaurant_id = Column(String, ForeignKey("restaurants.id"), nullable=False, index=True)
    category = Column(String(100))  # "pizza", "antipasti", "dolci", "bevande"
    name = Column(String(200), nullable=False)
    description = Column(Text)
    price = Column(Float)
    currency = Column(String(3), default="EUR")
    allergens = Column(JSON, default=[])  # ["gluten", "dairy", "nuts", ...]
    tags = Column(JSON, default=[])  # ["vegetarian", "vegan", "spicy", "popular"]
    available = Column(Boolean, default=True)
    image_url = Column(String(500))

    restaurant = relationship("Restaurant", back_populates="menu_items")


# ── Tables & Reservations ────────────────────────────────────────────

class Table(Base):
    __tablename__ = "tables"

    id = Column(String, primary_key=True, default=gen_uuid)
    restaurant_id = Column(String, ForeignKey("restaurants.id"), nullable=False, index=True)
    table_number = Column(Integer, nullable=False)
    capacity = Column(Integer, nullable=False)  # max seats
    location = Column(String(50))  # "indoor", "outdoor", "terrace"
    active = Column(Boolean, default=True)

    restaurant = relationship("Restaurant", back_populates="tables")

    __table_args__ = (
        UniqueConstraint("restaurant_id", "table_number", name="uq_restaurant_table"),
    )


class Reservation(Base):
    __tablename__ = "reservations"

    id = Column(String, primary_key=True, default=gen_uuid)
    restaurant_id = Column(String, ForeignKey("restaurants.id"), nullable=False, index=True)
    table_id = Column(String, ForeignKey("tables.id"), nullable=True)  # assigned later or auto
    guest_name = Column(String(200), nullable=False)
    guest_phone = Column(String(50))
    guest_email = Column(String(200))
    party_size = Column(Integer, nullable=False)
    date = Column(Date, nullable=False)
    time = Column(Time, nullable=False)
    duration_minutes = Column(Integer, default=90)
    status = Column(String(20), default="confirmed")  # confirmed, cancelled, completed, no_show
    notes = Column(Text)  # special requests
    source = Column(String(20), default="chatbot")  # chatbot, phone, walkin
    created_at = Column(DateTime, default=datetime.utcnow)

    restaurant = relationship("Restaurant", back_populates="reservations")


# ── FAQ ───────────────────────────────────────────────────────────────

class FAQ(Base):
    __tablename__ = "faqs"

    id = Column(String, primary_key=True, default=gen_uuid)
    restaurant_id = Column(String, ForeignKey("restaurants.id"), nullable=False, index=True)
    question = Column(Text, nullable=False)
    answer = Column(Text, nullable=False)
    language = Column(String(5), default="de")
    category = Column(String(50))  # "hours", "parking", "dietary", "events"

    restaurant = relationship("Restaurant", back_populates="faqs")


# ── Reviews (processed/summarized) ───────────────────────────────────

class Review(Base):
    __tablename__ = "reviews"

    id = Column(String, primary_key=True, default=gen_uuid)
    restaurant_id = Column(String, ForeignKey("restaurants.id"), nullable=False, index=True)
    source = Column(String(50))  # "google", "tripadvisor", "yelp"
    rating = Column(Float)
    text = Column(Text)
    dishes_mentioned = Column(JSON, default=[])  # ["margherita", "tiramisu"]
    sentiment = Column(String(20))  # "positive", "negative", "mixed"
    date = Column(Date)

    restaurant = relationship("Restaurant", back_populates="reviews")


# ── Conversation tracking ────────────────────────────────────────────

class Conversation(Base):
    __tablename__ = "conversations"

    id = Column(String, primary_key=True, default=gen_uuid)
    restaurant_id = Column(String, ForeignKey("restaurants.id"), nullable=False, index=True)
    session_id = Column(String(100), nullable=False, index=True)
    messages = Column(JSON, default=[])  # [{role, content, timestamp}, ...]
    language = Column(String(5))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    restaurant = relationship("Restaurant", back_populates="conversations")
