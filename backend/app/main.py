"""
FastAPI app — REST API for restaurant chatbot.
"""
import os
from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session
from dotenv import load_dotenv

load_dotenv()

from app.db import get_db
from app.models import Restaurant, MenuItem, Table, FAQ, Review
from app.schemas import ChatRequest, ChatResponse
from app.chat_engine import chat

app = FastAPI(title="Restaurant Bot API", version="0.1.0")

# CORS — allow widget from any origin
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Chat endpoint ────────────────────────────────────────────────────

@app.post("/api/chat", response_model=ChatResponse)
def chat_endpoint(req: ChatRequest, db: Session = Depends(get_db)):
    restaurant = db.query(Restaurant).filter(
        Restaurant.slug == req.restaurant_slug
    ).first()

    if not restaurant:
        raise HTTPException(404, f"Restaurant '{req.restaurant_slug}' not found")

    reply = chat(
        db=db,
        restaurant=restaurant,
        session_id=req.session_id,
        user_message=req.message,
        language=req.language,
    )

    return ChatResponse(reply=reply)


# ── Seed endpoint (call once after deploy to load Donna data) ────────

@app.post("/api/seed/{slug}")
def seed_restaurant(slug: str, db: Session = Depends(get_db)):
    """Load seed data from data/ directory. Call once after deploy."""
    import json
    from datetime import date as d

    data_path = os.path.join(os.path.dirname(__file__), "..", "..", "data", f"{slug.replace('-', '_')}_menu.json")

    # Try alternate path for Render's flat structure
    if not os.path.exists(data_path):
        data_path = os.path.join(os.path.dirname(__file__), "..", "data", f"{slug.replace('-', '_')}_menu.json")
    if not os.path.exists(data_path):
        # Try from project root
        for candidate in ["data/donna_menu.json", "../data/donna_menu.json", "../../data/donna_menu.json"]:
            if os.path.exists(candidate):
                data_path = candidate
                break

    if not os.path.exists(data_path):
        raise HTTPException(404, f"Seed file not found for '{slug}'")

    with open(data_path) as f:
        data = json.load(f)

    # Delete existing
    existing = db.query(Restaurant).filter(Restaurant.slug == slug).first()
    if existing:
        db.delete(existing)
        db.commit()

    r_data = data["restaurant"]
    restaurant = Restaurant(
        slug=r_data["slug"], name=r_data["name"], address=r_data["address"],
        phone=r_data["phone"], website=r_data.get("website"),
        languages=r_data["languages"], timezone=r_data["timezone"],
        opening_hours=r_data["opening_hours"], system_prompt=r_data["system_prompt"],
        config=r_data.get("config", {}),
    )
    db.add(restaurant)
    db.flush()

    for t in data["tables"]:
        db.add(Table(restaurant_id=restaurant.id, table_number=t["table_number"],
                     capacity=t["capacity"], location=t["location"]))

    for item in data["menu"]:
        db.add(MenuItem(restaurant_id=restaurant.id, category=item["category"],
                        name=item["name"], description=item["description"],
                        price=item["price"], allergens=item["allergens"], tags=item["tags"]))

    for faq in data["faqs"]:
        db.add(FAQ(restaurant_id=restaurant.id, question=faq["question"],
                   answer=faq["answer"], language=faq["language"], category=faq["category"]))

    for rev in data["reviews"]:
        db.add(Review(restaurant_id=restaurant.id, source=rev["source"],
                      rating=rev["rating"], text=rev["text"],
                      dishes_mentioned=rev["dishes_mentioned"],
                      sentiment=rev["sentiment"], date=d.fromisoformat(rev["date"])))

    db.commit()
    return {"status": "ok", "restaurant": restaurant.name, "slug": slug}


# ── Health check ─────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok"}


# ── Restaurant info (public) ─────────────────────────────────────────

@app.get("/api/restaurant/{slug}")
def get_restaurant(slug: str, db: Session = Depends(get_db)):
    r = db.query(Restaurant).filter(Restaurant.slug == slug).first()
    if not r:
        raise HTTPException(404)
    return {
        "name": r.name,
        "address": r.address,
        "phone": r.phone,
        "languages": r.languages,
        "opening_hours": r.opening_hours,
    }
