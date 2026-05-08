from connection import get_connection

CREATE_INVENTORY_ITEMS = """
CREATE TABLE IF NOT EXISTS inventory_items (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    quantity INTEGER NOT NULL,
    shelf_life_days INTEGER,
    date_received DATE DEFAULT CURRENT_DATE,
    expiry_date DATE,
    created_at TIMESTAMP DEFAULT NOW()
);
"""

CREATE_SHELF_LIFE_REFERENCE = """
CREATE TABLE IF NOT EXISTS shelf_life_reference (
    id SERIAL PRIMARY KEY,
    name VARCHAR(255) NOT NULL,
    shelf_life_days INTEGER NOT NULL,
    storage_type VARCHAR(50)
);
"""

SEED_DATA = [
    ("egg", 21, "refrigerated"),
    ("carrot", 30, "refrigerated"),
    ("onion", 30, "room_temp"),
    ("tomato", 7, "room_temp"),
    ("potato", 30, "room_temp"),
    ("cabbage", 14, "refrigerated"),
    ("garlic", 90, "room_temp"),
    ("ginger", 14, "room_temp"),
]

def seed():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute(CREATE_INVENTORY_ITEMS)
    cur.execute(CREATE_SHELF_LIFE_REFERENCE)

    cur.execute("SELECT COUNT(*) FROM shelf_life_reference")
    count = cur.fetchone()[0]
    if count == 0:
        cur.executemany(
            "INSERT INTO shelf_life_reference (name, shelf_life_days, storage_type) VALUES (%s, %s, %s)",
            SEED_DATA,
        )
        print(f"Seeded {len(SEED_DATA)} shelf_life_reference rows.")
    else:
        print("shelf_life_reference already seeded, skipping.")

    conn.commit()
    cur.close()
    conn.close()
    print("Database setup complete.")

if __name__ == "__main__":
    seed()
