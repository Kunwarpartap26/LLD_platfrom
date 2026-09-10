"""Seed the three LLD problems. Safe to run repeatedly (idempotent by title)."""

from sqlalchemy.orm import Session

from database import Base, SessionLocal, engine
from models import Problem

PROBLEMS: list[dict[str, str]] = [
    {
        "title": "Parking Lot System",
        "description": "Design a parking lot system that manages vehicle parking across multiple floors.",
        "requirements": "\n".join(
            [
                "- Support multiple floors with multiple parking spots per floor",
                "- Support different vehicle types: Motorcycle, Car, Truck",
                "- Different spot sizes: Small (motorcycle), Medium (car), Large (truck)",
                "- A vehicle can only park in a spot that fits its size or larger",
                "- Track which spots are occupied and which are free",
                "- Generate a parking ticket when a vehicle parks",
                "- Calculate parking fee when vehicle exits (hourly rate by vehicle type)",
                "- Find nearest available spot for a vehicle type",
                "- Support for handicapped spots (reserved, can park any vehicle with permit)",
            ]
        ),
        "constraints": "\n".join(
            [
                "- A spot can only hold one vehicle at a time",
                "- A ticket must be issued for every parked vehicle",
                "- Fee calculation: Motorcycle $1/hr, Car $2/hr, Truck $3/hr",
                "- System must handle concurrent requests (mention how you'd handle this)",
                "- Parking lot can be full — system must handle this case",
            ]
        ),
    },
    {
        "title": "Elevator System",
        "description": "Design an elevator control system for a multi-floor building with multiple elevators.",
        "requirements": "\n".join(
            [
                "- Support multiple elevators in one building",
                "- Each elevator has a maximum weight capacity and max passenger count",
                "- Elevators can move Up, Down, or stay Idle",
                "- Users press Up or Down buttons on each floor to request an elevator",
                "- Users press floor buttons inside elevator to select destination",
                "- System dispatches the most suitable elevator to a floor request",
                "- Track current floor and direction of each elevator",
                "- Handle doors: open when arrived, close before moving",
                "- Emergency stop button inside each elevator",
            ]
        ),
        "constraints": "\n".join(
            [
                "- An elevator cannot move if doors are open",
                "- Elevator cannot exceed weight or passenger capacity",
                "- If all elevators are busy, requests must be queued",
                "- System should minimize total travel distance across all elevators",
                "- Emergency stop overrides all other commands",
            ]
        ),
    },
    {
        "title": "Vending Machine",
        "description": "Design a vending machine that dispenses products and handles payments.",
        "requirements": "\n".join(
            [
                "- Machine holds multiple product types in separate slots",
                "- Each slot has a product type, price, and quantity",
                "- Support payment methods: coins and notes",
                "- User selects a product, inserts money, machine dispenses product and gives change",
                "- Admin can restock products and collect money",
                "- Display current inventory and prices",
                "- Handle insufficient funds gracefully",
                "- Handle out of stock gracefully",
                "- Track all transactions",
            ]
        ),
        "constraints": "\n".join(
            [
                "- Machine must always be able to give change if it has sufficient coins",
                "- If machine cannot give exact change, reject the transaction",
                "- Product is only dispensed after full payment is confirmed",
                "- Admin operations require a separate admin mode/code",
                "- Machine state must be consistent — no partial transactions",
            ]
        ),
    },
]


def seed_problems(db: Session) -> int:
    """Insert any problems not already present. Returns number inserted."""
    existing_titles = {title for (title,) in db.query(Problem.title).all()}
    inserted = 0
    for data in PROBLEMS:
        if data["title"] in existing_titles:
            continue
        db.add(Problem(**data))
        inserted += 1
    db.commit()
    return inserted


def seed_if_empty(db: Session) -> int:
    """Startup hook: only seed when the problems table is empty."""
    if db.query(Problem).count() > 0:
        return 0
    return seed_problems(db)


if __name__ == "__main__":
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    try:
        count = seed_problems(session)
        print(f"Seeded {count} new problem(s). Total: {session.query(Problem).count()}")
    finally:
        session.close()
