"""
Reservation logic: availability check, booking, cancellation.
"""
from datetime import date, time, datetime, timedelta
from sqlalchemy.orm import Session
from sqlalchemy import and_
from app.models import Restaurant, Table, Reservation


def check_availability(
    db: Session,
    restaurant_id: str,
    req_date: date,
    req_time: time,
    party_size: int,
    duration_minutes: int = 90
) -> list[dict]:
    """Return available tables for given date/time/party size."""
    restaurant = db.query(Restaurant).get(restaurant_id)
    if not restaurant:
        return []

    # Check if restaurant is open on that day
    day_name = req_date.strftime("%a").lower()  # "mon", "tue", ...
    hours = (restaurant.opening_hours or {}).get(day_name)
    if not hours:
        return []  # closed that day

    open_time = _parse_time(hours.get("open", "00:00"))
    close_time = _parse_time(hours.get("close", "23:59"))
    if req_time < open_time or req_time > close_time:
        return []  # outside hours

    # Find tables big enough
    tables = db.query(Table).filter(
        Table.restaurant_id == restaurant_id,
        Table.capacity >= party_size,
        Table.active == True
    ).all()

    available = []
    for table in tables:
        if _is_table_free(db, table.id, req_date, req_time, duration_minutes):
            available.append({
                "table_id": table.id,
                "table_number": table.table_number,
                "capacity": table.capacity,
                "location": table.location,
            })

    return available


def create_reservation(
    db: Session,
    restaurant_id: str,
    guest_name: str,
    party_size: int,
    req_date: date,
    req_time: time,
    guest_phone: str = None,
    guest_email: str = None,
    notes: str = None,
    duration_minutes: int = 90,
) -> dict:
    """Book a table. Auto-assigns best fit table."""
    available = check_availability(db, restaurant_id, req_date, req_time, party_size, duration_minutes)
    if not available:
        return {"success": False, "error": "no_availability",
                "message": "No tables available for that date/time/party size."}

    # Pick smallest suitable table (waste least capacity)
    best = min(available, key=lambda t: t["capacity"])

    reservation = Reservation(
        restaurant_id=restaurant_id,
        table_id=best["table_id"],
        guest_name=guest_name,
        guest_phone=guest_phone,
        guest_email=guest_email,
        party_size=party_size,
        date=req_date,
        time=req_time,
        duration_minutes=duration_minutes,
        notes=notes,
        status="confirmed",
        source="chatbot",
    )
    db.add(reservation)
    db.commit()
    db.refresh(reservation)

    return {
        "success": True,
        "reservation_id": reservation.id,
        "table_number": best["table_number"],
        "location": best["location"],
        "date": str(req_date),
        "time": str(req_time),
        "party_size": party_size,
        "guest_name": guest_name,
    }


def cancel_reservation(db: Session, reservation_id: str) -> dict:
    res = db.query(Reservation).get(reservation_id)
    if not res:
        return {"success": False, "error": "not_found"}
    res.status = "cancelled"
    db.commit()
    return {"success": True, "reservation_id": reservation_id}


def get_available_slots(
    db: Session,
    restaurant_id: str,
    req_date: date,
    party_size: int,
    interval_minutes: int = 30
) -> list[str]:
    """Return all available time slots for a given date and party size."""
    restaurant = db.query(Restaurant).get(restaurant_id)
    if not restaurant:
        return []

    day_name = req_date.strftime("%a").lower()
    hours = (restaurant.opening_hours or {}).get(day_name)
    if not hours:
        return []

    open_time = _parse_time(hours["open"])
    close_time = _parse_time(hours["close"])

    slots = []
    current = datetime.combine(req_date, open_time)
    end = datetime.combine(req_date, close_time) - timedelta(minutes=90)  # last seating

    while current <= end:
        t = current.time()
        avail = check_availability(db, restaurant_id, req_date, t, party_size)
        if avail:
            slots.append(t.strftime("%H:%M"))
        current += timedelta(minutes=interval_minutes)

    return slots


# ── Helpers ───────────────────────────────────────────────────────────

def _is_table_free(
    db: Session, table_id: str, req_date: date, req_time: time, duration: int
) -> bool:
    """Check no overlapping confirmed reservations."""
    req_start = datetime.combine(req_date, req_time)
    req_end = req_start + timedelta(minutes=duration)

    conflicts = db.query(Reservation).filter(
        Reservation.table_id == table_id,
        Reservation.date == req_date,
        Reservation.status.in_(["confirmed"]),
    ).all()

    for res in conflicts:
        res_start = datetime.combine(res.date, res.time)
        res_end = res_start + timedelta(minutes=res.duration_minutes or 90)
        # Overlap check
        if req_start < res_end and req_end > res_start:
            return False

    return True


def _parse_time(t_str: str) -> time:
    parts = t_str.split(":")
    return time(int(parts[0]), int(parts[1]))
