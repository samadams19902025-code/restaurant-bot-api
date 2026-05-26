"""
Menu search, allergen filtering, review-based recommendations.
"""
from sqlalchemy.orm import Session
from app.models import MenuItem, Review


def get_menu(db: Session, restaurant_id: str, category: str = None) -> list[dict]:
    q = db.query(MenuItem).filter(
        MenuItem.restaurant_id == restaurant_id,
        MenuItem.available == True
    )
    if category:
        q = q.filter(MenuItem.category == category)
    return [_item_to_dict(item) for item in q.all()]


def filter_by_allergens(db: Session, restaurant_id: str, exclude: list[str]) -> list[dict]:
    """Return menu items that do NOT contain any of the excluded allergens."""
    items = db.query(MenuItem).filter(
        MenuItem.restaurant_id == restaurant_id,
        MenuItem.available == True
    ).all()

    safe = []
    for item in items:
        item_allergens = set(a.lower() for a in (item.allergens or []))
        excluded = set(a.lower() for a in exclude)
        if not item_allergens.intersection(excluded):
            safe.append(_item_to_dict(item))
    return safe


def get_popular_dishes(db: Session, restaurant_id: str, limit: int = 5) -> list[dict]:
    """Dishes most mentioned positively in reviews."""
    reviews = db.query(Review).filter(
        Review.restaurant_id == restaurant_id,
        Review.sentiment == "positive"
    ).all()

    dish_count: dict[str, int] = {}
    for r in reviews:
        for dish in (r.dishes_mentioned or []):
            dish_count[dish.lower()] = dish_count.get(dish.lower(), 0) + 1

    top = sorted(dish_count.items(), key=lambda x: -x[1])[:limit]
    top_names = [name for name, _ in top]

    # Match to actual menu items
    items = db.query(MenuItem).filter(
        MenuItem.restaurant_id == restaurant_id,
        MenuItem.available == True
    ).all()

    result = []
    for item in items:
        if item.name.lower() in top_names:
            d = _item_to_dict(item)
            d["mention_count"] = dish_count.get(item.name.lower(), 0)
            result.append(d)

    return sorted(result, key=lambda x: -x.get("mention_count", 0))


def search_menu(db: Session, restaurant_id: str, query: str) -> list[dict]:
    """Simple text search on name/description."""
    items = db.query(MenuItem).filter(
        MenuItem.restaurant_id == restaurant_id,
        MenuItem.available == True
    ).all()

    q = query.lower()
    return [_item_to_dict(i) for i in items
            if q in (i.name or "").lower() or q in (i.description or "").lower()]


def _item_to_dict(item: MenuItem) -> dict:
    return {
        "id": item.id,
        "name": item.name,
        "category": item.category,
        "description": item.description,
        "price": item.price,
        "allergens": item.allergens or [],
        "tags": item.tags or [],
    }
