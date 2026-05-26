"""
Chat engine: orchestrates Claude API with tool use for restaurant operations.
LLM decides when to search menu, check allergens, make reservations, etc.
"""
import os
import json
from datetime import datetime
from anthropic import Anthropic
from sqlalchemy.orm import Session
from app.models import Restaurant, Conversation, FAQ
from app import menu as menu_service
from app import reservation as res_service

client = Anthropic(api_key=os.getenv("ANTHROPIC_API_KEY"))
MODEL = os.getenv("DEFAULT_MODEL", "claude-sonnet-4-20250514")

# ── Tool definitions (Claude function calling) ───────────────────────

TOOLS = [
    {
        "name": "search_menu",
        "description": "Search menu items by keyword (e.g. 'margherita', 'vegetarian', 'dessert')",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "Search term"},
                "category": {"type": "string", "description": "Category filter: pizza, antipasti, primi, secondi, dolci, bevande"}
            },
            "required": ["query"]
        }
    },
    {
        "name": "filter_allergens",
        "description": "Find menu items safe for guests with specific allergies/intolerances. Call this when guest mentions allergies.",
        "input_schema": {
            "type": "object",
            "properties": {
                "exclude_allergens": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Allergens to exclude: gluten, dairy, nuts, eggs, fish, shellfish, soy, celery, mustard, sesame, lupin, mollusks"
                }
            },
            "required": ["exclude_allergens"]
        }
    },
    {
        "name": "get_popular_dishes",
        "description": "Get most recommended dishes based on customer reviews. Use when guest asks 'what should I order?' or wants recommendations.",
        "input_schema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "description": "Number of recommendations", "default": 5}
            }
        }
    },
    {
        "name": "check_availability",
        "description": "Check if tables are available for a specific date, time, and party size.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "Date in YYYY-MM-DD format"},
                "time": {"type": "string", "description": "Time in HH:MM format"},
                "party_size": {"type": "integer", "description": "Number of guests"}
            },
            "required": ["date", "time", "party_size"]
        }
    },
    {
        "name": "create_reservation",
        "description": "Create a table reservation. Only call AFTER confirming all details with the guest.",
        "input_schema": {
            "type": "object",
            "properties": {
                "guest_name": {"type": "string"},
                "party_size": {"type": "integer"},
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "time": {"type": "string", "description": "HH:MM"},
                "guest_phone": {"type": "string"},
                "guest_email": {"type": "string"},
                "notes": {"type": "string", "description": "Special requests (e.g. high chair, birthday)"}
            },
            "required": ["guest_name", "party_size", "date", "time"]
        }
    },
    {
        "name": "get_available_slots",
        "description": "List all available time slots for a date and party size. Use when guest is flexible on time.",
        "input_schema": {
            "type": "object",
            "properties": {
                "date": {"type": "string", "description": "YYYY-MM-DD"},
                "party_size": {"type": "integer"}
            },
            "required": ["date", "party_size"]
        }
    },
    {
        "name": "get_full_menu",
        "description": "Get the complete menu or a specific category. Use when guest asks to see the menu.",
        "input_schema": {
            "type": "object",
            "properties": {
                "category": {"type": "string", "description": "Optional: pizza, antipasti, primi, secondi, dolci, bevande"}
            }
        }
    }
]


def build_system_prompt(restaurant: Restaurant, language: str) -> str:
    """Build system prompt from restaurant config."""
    lang_map = {"de": "German", "en": "English", "it": "Italian"}
    lang_name = lang_map.get(language, "German")

    base = f"""You are the friendly virtual assistant for {restaurant.name}.
You help guests with:
1. Table reservations — collect date, time, party size, name, and optional phone/notes
2. Menu recommendations — suggest dishes based on reviews and preferences
3. Allergen/dietary information — filter menu for allergies and intolerances
4. General questions — opening hours, location, parking, events, etc.

IMPORTANT RULES:
- Respond in {lang_name}
- Be warm, concise, and helpful — like a good host
- For reservations: always confirm all details before calling create_reservation
- For allergens: always ask which specific allergies before filtering
- Today's date is {datetime.now().strftime('%Y-%m-%d')}
- If you don't know something, say so honestly
- Never invent menu items or prices — only use data from tools
- Format prices as €X.XX

RESTAURANT INFO:
- Name: {restaurant.name}
- Address: {restaurant.address or 'N/A'}
- Phone: {restaurant.phone or 'N/A'}
"""

    if restaurant.opening_hours:
        base += f"\nOpening hours: {json.dumps(restaurant.opening_hours, indent=2)}"

    # Append custom instructions from restaurant owner
    if restaurant.system_prompt:
        base += f"\n\nADDITIONAL INSTRUCTIONS FROM RESTAURANT:\n{restaurant.system_prompt}"

    return base


def handle_tool_call(tool_name: str, tool_input: dict, db: Session, restaurant_id: str) -> str:
    """Execute a tool call and return result as string."""
    try:
        if tool_name == "search_menu":
            results = menu_service.search_menu(db, restaurant_id, tool_input["query"])
            return json.dumps(results, ensure_ascii=False)

        elif tool_name == "filter_allergens":
            results = menu_service.filter_by_allergens(db, restaurant_id, tool_input["exclude_allergens"])
            return json.dumps(results, ensure_ascii=False)

        elif tool_name == "get_popular_dishes":
            results = menu_service.get_popular_dishes(db, restaurant_id, tool_input.get("limit", 5))
            return json.dumps(results, ensure_ascii=False)

        elif tool_name == "get_full_menu":
            results = menu_service.get_menu(db, restaurant_id, tool_input.get("category"))
            return json.dumps(results, ensure_ascii=False)

        elif tool_name == "check_availability":
            from datetime import date as d, time as t
            req_date = d.fromisoformat(tool_input["date"])
            req_time = t.fromisoformat(tool_input["time"])
            results = res_service.check_availability(
                db, restaurant_id, req_date, req_time, tool_input["party_size"]
            )
            if results:
                return json.dumps({"available": True, "tables": results}, ensure_ascii=False)
            return json.dumps({"available": False, "tables": []})

        elif tool_name == "create_reservation":
            from datetime import date as d, time as t
            result = res_service.create_reservation(
                db, restaurant_id,
                guest_name=tool_input["guest_name"],
                party_size=tool_input["party_size"],
                req_date=d.fromisoformat(tool_input["date"]),
                req_time=t.fromisoformat(tool_input["time"]),
                guest_phone=tool_input.get("guest_phone"),
                guest_email=tool_input.get("guest_email"),
                notes=tool_input.get("notes"),
            )
            return json.dumps(result, ensure_ascii=False)

        elif tool_name == "get_available_slots":
            from datetime import date as d
            slots = res_service.get_available_slots(
                db, restaurant_id,
                d.fromisoformat(tool_input["date"]),
                tool_input["party_size"]
            )
            return json.dumps({"slots": slots})

        else:
            return json.dumps({"error": f"Unknown tool: {tool_name}"})

    except Exception as e:
        return json.dumps({"error": str(e)})


def chat(
    db: Session,
    restaurant: Restaurant,
    session_id: str,
    user_message: str,
    language: str = "de"
) -> str:
    """Main chat function. Handles multi-turn conversation with tool use."""

    # Load or create conversation
    convo = db.query(Conversation).filter(
        Conversation.restaurant_id == restaurant.id,
        Conversation.session_id == session_id
    ).first()

    if not convo:
        convo = Conversation(
            restaurant_id=restaurant.id,
            session_id=session_id,
            messages=[],
            language=language,
        )
        db.add(convo)
        db.commit()
        db.refresh(convo)

    # Load FAQ context
    faqs = db.query(FAQ).filter(FAQ.restaurant_id == restaurant.id).all()
    faq_context = ""
    if faqs:
        faq_context = "\n\nFREQUENTLY ASKED QUESTIONS:\n"
        for f in faqs:
            faq_context += f"Q: {f.question}\nA: {f.answer}\n\n"

    system_prompt = build_system_prompt(restaurant, language) + faq_context

    # Build messages history
    history = convo.messages or []
    messages = []
    for msg in history[-20:]:  # keep last 20 messages for context
        messages.append({"role": msg["role"], "content": msg["content"]})
    messages.append({"role": "user", "content": user_message})

    # Call Claude with tools
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=system_prompt,
        tools=TOOLS,
        messages=messages,
    )

    # Handle tool use loop (Claude may call multiple tools)
    while response.stop_reason == "tool_use":
        tool_blocks = [b for b in response.content if b.type == "tool_use"]

        # Add assistant response to messages
        messages.append({"role": "assistant", "content": response.content})

        # Process each tool call
        tool_results = []
        for block in tool_blocks:
            result = handle_tool_call(block.name, block.input, db, restaurant.id)
            tool_results.append({
                "type": "tool_result",
                "tool_use_id": block.id,
                "content": result,
            })

        messages.append({"role": "user", "content": tool_results})

        # Continue conversation
        response = client.messages.create(
            model=MODEL,
            max_tokens=1024,
            system=system_prompt,
            tools=TOOLS,
            messages=messages,
        )

    # Extract final text response
    reply = ""
    for block in response.content:
        if hasattr(block, "text"):
            reply += block.text

    # Save conversation
    history.append({"role": "user", "content": user_message, "ts": datetime.utcnow().isoformat()})
    history.append({"role": "assistant", "content": reply, "ts": datetime.utcnow().isoformat()})
    convo.messages = history
    convo.updated_at = datetime.utcnow()
    db.commit()

    return reply
