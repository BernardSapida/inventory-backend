"""
Full seed: Firebase Auth users, Firestore users, products, inventory_batches,
recipes, and preparations (production history).

Design goals:
  - 4 recipe categories: Appetizer, Main Course, Side Dish, Dessert (24 recipes)
  - Meat products use specific cuts (Chicken Thigh, Chicken Wings, Beef Shank, etc.)
  - measurable=True  → item can be used in different units (ml, g, L, tbsp…)
                       needs unitSize (how many usageUnits per 1 purchaseUnit)
  - measurable=False → item is always in pcs (egg, garlic, vegetables, fruits…)
  - Condiments and dairy tracked in pcs (bottles/cans), usageUnit for recipes = ml/g
  - used_stock collection seeded with realistic partial-bottle values
  - Coconut Milk has no batch → OUT OF STOCK
  - 30 preparation records, 2 seeded users (admin + staff)
  - Idempotent: deterministic doc IDs, safe to re-run

Usage (from inventory-backend/):
  venv/Scripts/python.exe scripts/seed_data.py              # dry run
  venv/Scripts/python.exe scripts/seed_data.py --commit     # write to Firestore
"""

import datetime
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))

from firebase_admin import auth as fb_auth, firestore as fb_fs  # noqa: E402

from db.connection import get_db  # noqa: E402

COMMIT = "--commit" in sys.argv
TODAY = datetime.date.today()


# ── unit helpers ──────────────────────────────────────────────────────────────

_UNIT = {
    "g": ("g", 1), "kg": ("g", 1000), "mg": ("g", 0.001),
    "ml": ("ml", 1), "L": ("ml", 1000),
    "tbsp": ("ml", 14.787), "tsp": ("ml", 4.929), "cup": ("ml", 240), "oz": ("ml", 29.574),
    "pcs": ("piece", 1),
}


def base_unit(du):
    return _UNIT.get(du, ("piece", 1))[0]


def to_base(value, du):
    return value * _UNIT.get(du, ("piece", 1))[1]


def ts(d):
    """date → UTC datetime for Firestore."""
    return datetime.datetime(d.year, d.month, d.day, tzinfo=datetime.timezone.utc)


# ── USERS ─────────────────────────────────────────────────────────────────────

_ADMIN_PERMS = {
    "inventoryView": True, "inventoryAdjust": True, "recipePrepare": True,
    "inspectionSubmit": True, "notificationsView": True, "forecastView": True, "staffManage": True,
}
_STAFF_PERMS = {
    "inventoryView": True, "inventoryAdjust": True, "recipePrepare": True,
    "inspectionSubmit": True, "notificationsView": True, "forecastView": False, "staffManage": False,
}

SEED_USERS = [
    {
        "email": "admin@gmail.com",
        "password": "@Password123",
        "fullName": "Smith Doe",
        "role": "admin",
        "permissions": _ADMIN_PERMS,
    },
    {
        "email": "staff@gmail.com",
        "password": "@Password123",
        "fullName": "John Doe",
        "role": "staff",
        "permissions": _STAFF_PERMS,
    },
]


# ── PRODUCTS ──────────────────────────────────────────────────────────────────
# (name, category, displayUnit, minThresholdDisplay, shelfLifeDays, measurable, unitSize, usageUnit)
#
# measurable=True  → item can be measured in different units in recipes
#                    unitSize = how many usageUnits are in 1 displayUnit
#                    e.g. 1 bottle Soy Sauce = 750ml → unitSize=750, usageUnit="ml"
#                    e.g. 1 kg Chicken = 1000g       → unitSize=1000, usageUnit="g"
# measurable=False → item is always pcs in recipes (egg, garlic, vegetables…)
#                    unitSize=None, usageUnit="pcs"

SEED_PRODUCTS = [

    # ── Meat (specific cuts) ──────────────────────────────────────────────────
    # Chicken
    ("Chicken Breast",    "Meat", "kg",  0.3,  3, True,  1000, "g"),
    ("Chicken Thigh",     "Meat", "kg",  0.3,  3, True,  1000, "g"),
    ("Chicken Wings",     "Meat", "kg",  0.3,  3, True,  1000, "g"),
    ("Chicken Drumstick", "Meat", "kg",  0.3,  3, True,  1000, "g"),
    ("Chicken Neck",      "Meat", "kg",  0.2,  3, True,  1000, "g"),
    ("Chicken Feet",      "Meat", "kg",  0.2,  3, True,  1000, "g"),
    ("Chicken Liver",     "Meat", "kg",  0.2,  2, True,  1000, "g"),
    # Pork
    ("Ground Pork",       "Meat", "kg",  0.3,  2, True,  1000, "g"),
    ("Pork Belly",        "Meat", "kg",  0.5,  3, True,  1000, "g"),
    ("Pork Ribs",         "Meat", "kg",  0.5,  3, True,  1000, "g"),
    ("Pork Shoulder",     "Meat", "kg",  0.5,  3, True,  1000, "g"),
    # Beef
    ("Beef Brisket",      "Meat", "kg",  0.5,  3, True,  1000, "g"),
    ("Beef Shank",        "Meat", "kg",  0.5,  3, True,  1000, "g"),
    ("Ground Beef",       "Meat", "kg",  0.3,  2, True,  1000, "g"),

    # ── Seafood ───────────────────────────────────────────────────────────────
    ("Bangus",            "Seafood",  "kg",  0.3,  2, True,  1000, "g"),
    ("Shrimp",            "Seafood",  "kg",  0.3,  2, True,  1000, "g"),

    # ── Vegetables (all pcs - countable, not measurable) ─────────────────────
    ("Ampalaya",          "Vegetables", "pcs",  2,  5, False, None, "pcs"),
    ("Bean Sprout",       "Vegetables", "g",   50,  3, True,  1,    "g"),
    ("Bell Pepper",       "Vegetables", "pcs",  2,  7, False, None, "pcs"),
    ("Carrot",            "Vegetables", "pcs",  3, 14, False, None, "pcs"),
    ("Eggplant",          "Vegetables", "pcs",  2,  5, False, None, "pcs"),
    ("Garlic",            "Vegetables", "pcs",  5, 30, False, None, "pcs"),
    ("Ginger",            "Vegetables", "pcs",  3, 14, False, None, "pcs"),
    ("Green Papaya",      "Vegetables", "pcs",  1,  7, False, None, "pcs"),
    ("Kalabasa",          "Vegetables", "pcs",  1,  7, False, None, "pcs"),
    ("Kangkong",          "Vegetables", "pcs",  2,  3, False, None, "pcs"),
    ("Okra",              "Vegetables", "pcs",  5,  5, False, None, "pcs"),
    ("Onion",             "Vegetables", "pcs",  5, 14, False, None, "pcs"),
    ("Pechay",            "Vegetables", "pcs",  2,  3, False, None, "pcs"),
    ("Potato",            "Vegetables", "pcs",  3, 10, False, None, "pcs"),
    ("Sitaw",             "Vegetables", "pcs",  5,  5, False, None, "pcs"),
    ("Tomato",            "Vegetables", "pcs",  5,  5, False, None, "pcs"),

    # ── Fruits (all pcs) ──────────────────────────────────────────────────────
    ("Banana",            "Fruits", "pcs",  5,  5, False, None, "pcs"),
    ("Calamansi",         "Fruits", "pcs",  5,  7, False, None, "pcs"),
    ("Green Mango",       "Fruits", "pcs",  3,  7, False, None, "pcs"),
    ("Lemon",             "Fruits", "pcs",  3,  7, False, None, "pcs"),
    ("Mango",             "Fruits", "pcs",  3,  5, False, None, "pcs"),
    ("Young Coconut",     "Fruits", "pcs",  2,  5, False, None, "pcs"),

    # ── Condiments (pcs/bottles/cans - measurable, usageUnit=ml or g) ─────────
    ("Cooking Oil",       "Condiments", "pcs",  1, 365, True, 1000, "ml"),  # 1L bottle
    ("Fish Sauce",        "Condiments", "pcs",  1, 365, True,  700, "ml"),  # 700ml bottle
    ("Liver Spread",      "Condiments", "pcs",  2, 180, True,  100, "g"),   # 100g can
    ("Oyster Sauce",      "Condiments", "pcs",  1, 180, True,  350, "ml"),  # 350ml bottle
    ("Sesame Oil",        "Condiments", "pcs",  1, 365, True,  150, "ml"),  # 150ml bottle
    ("Soy Sauce",         "Condiments", "pcs",  1, 365, True,  750, "ml"),  # 750ml bottle
    ("Tomato Paste",      "Condiments", "pcs",  2, 180, True,  150, "g"),   # 150g can
    ("Vinegar",           "Condiments", "pcs",  1, 730, True,  750, "ml"),  # 750ml bottle

    # ── Dry Goods ─────────────────────────────────────────────────────────────
    ("All-Purpose Flour", "Dry Goods", "g",   200, 180, True,  1,    "g"),
    ("Cornstarch",        "Dry Goods", "g",   100, 365, True,  1,    "g"),
    ("Gulaman",           "Dry Goods", "g",    30, 180, True,  1,    "g"),
    ("Lumpia Wrapper",    "Dry Goods", "pcs",  10,  30, False, None, "pcs"),
    ("Mung Bean",         "Dry Goods", "g",   100, 365, True,  1,    "g"),
    ("Rice",              "Dry Goods", "kg",    2, 180, True,  1000, "g"),
    ("Rice Flour",        "Dry Goods", "g",   200, 180, True,  1,    "g"),
    ("Sago Pearl",        "Dry Goods", "g",    50, 365, True,  1,    "g"),
    ("Sugar",             "Dry Goods", "kg",  0.5, 365, True,  1000, "g"),
    ("Wonton Wrapper",    "Dry Goods", "pcs",  20,  30, False, None, "pcs"),

    # ── Dairy ─────────────────────────────────────────────────────────────────
    ("All-Purpose Cream", "Dairy", "pcs",  1,  30, True,  250, "ml"),  # 250ml pack
    ("Coconut Milk",      "Dairy", "pcs",  2,  90, True,  400, "ml"),  # 400ml can - NO BATCH
    ("Condensed Milk",    "Dairy", "pcs",  2, 365, True,  390, "ml"),  # 390ml can
    ("Egg",               "Dairy", "pcs",  6,  21, False, None, "pcs"),
    ("Evaporated Milk",   "Dairy", "pcs",  3, 365, True,  370, "ml"),  # 370ml can

    # ── Pantry ────────────────────────────────────────────────────────────────
    ("Bay Leaf",          "Pantry", "pcs",  5, 180, False, None, "pcs"),
    ("Black Pepper",      "Pantry", "g",   30, 365, True,  1,    "g"),
    ("Salt",              "Pantry", "g",  100, 730, True,  1,    "g"),
    ("Tofu",              "Pantry", "pcs",  2,   7, False, None, "pcs"),

    # ── Seasonings ────────────────────────────────────────────────────────────
    ("Annatto Powder",    "Seasonings", "g",   20, 180, True,  1,    "g"),
    ("Bagoong Alamang",   "Seasonings", "g",   50,  90, True,  1,    "g"),
    ("Pandan Leaf",       "Seasonings", "pcs",  5,   7, False, None, "pcs"),
]


# ── INVENTORY BATCHES ─────────────────────────────────────────────────────────
# (product_name, quantity_in_purchase_units, expiry_date, location)
# Meat/Seafood (kg): quantity in grams (base unit)
# Condiments/Dairy (pcs): quantity in pieces (bottles/cans/packs)
# g products: quantity in grams
# kg dry goods: quantity in grams
#
# Intentionally LOW totals:
#   Ground Pork  400g  (1 batch) → Lumpia Shanghai = 4        ← LOW
#   Beef Brisket 750g  (2 batches)→ Kare-Kare/Caldereta = 3  ← LOW
#   Beef Shank   750g  (2 batches)→ Bulalo = 3               ← LOW
#   Bangus       600g  (1 batch) → Kinilaw = 3               ← LOW
#   Egg          14pcs (2 batches)→ Leche Flan = 3           ← LOW
#   Green Mango  6pcs  (2 batches)→ Ensaladang Mangga = 6    ← LOW
#   Coconut Milk (0 batches)     → Bibingka/Maja Blanca = 0  ← ALERT

def _exp(n):
    return ts(TODAY + datetime.timedelta(days=n))


SEED_BATCHES = [

    # ── Meat ─────────────────────────────────────────────────────────────────

    # Chicken Thigh - 2 batches (Adobong Manok + Chicken Inasal)
    ("Chicken Thigh",     1500, _exp(2),  "Freezer A"),
    ("Chicken Thigh",     1500, _exp(5),  "Freezer A"),

    # Chicken Wings - 2 batches (Tinolang Manok) → ~8 servings (2000g ÷ 250g)
    ("Chicken Wings",      800, _exp(2),  "Freezer A"),
    ("Chicken Wings",     1200, _exp(4),  "Freezer A"),

    # Chicken Breast - 2 batches (stock only)
    ("Chicken Breast",    1000, _exp(2),  "Freezer B"),
    ("Chicken Breast",    1000, _exp(5),  "Freezer B"),

    # Other chicken cuts - 1 batch each (stock only)
    ("Chicken Drumstick",  800, _exp(3),  "Freezer B"),
    ("Chicken Neck",       500, _exp(2),  "Freezer B"),
    ("Chicken Feet",       500, _exp(3),  "Freezer B"),
    ("Chicken Liver",      400, _exp(2),  "Freezer B"),

    # Pork
    ("Pork Belly",        1500, _exp(1),  "Freezer A"),
    ("Pork Belly",        1500, _exp(3),  "Freezer A"),
    ("Pork Belly",        1500, _exp(5),  "Freezer B"),
    ("Ground Pork",        450, _exp(1),  "Freezer B"),   # → ~9 servings Lumpia Shanghai (900g ÷ 100g)
    ("Ground Pork",        450, _exp(3),  "Freezer B"),
    ("Pork Ribs",         1000, _exp(3),  "Freezer A"),
    ("Pork Shoulder",     1500, _exp(4),  "Freezer A"),

    # Beef - Brisket (Kare-Kare ~10, Caldereta ~12), Shank (Bulalo ~8)
    ("Beef Brisket",       800, _exp(2),  "Freezer A"),   # total = 2500g → Kare-Kare=10, Caldereta=12
    ("Beef Brisket",       900, _exp(4),  "Freezer A"),
    ("Beef Brisket",       800, _exp(7),  "Freezer A"),
    ("Beef Shank",        1000, _exp(2),  "Freezer A"),   # total = 2000g → Bulalo=8
    ("Beef Shank",        1000, _exp(5),  "Freezer A"),
    ("Ground Beef",        600, _exp(2),  "Freezer B"),

    # ── Seafood ──────────────────────────────────────────────────────────────
    ("Bangus",             800, _exp(1),  "Freezer B"),   # total = 1600g → Kinilaw=8
    ("Bangus",             800, _exp(3),  "Freezer B"),
    ("Shrimp",             500, _exp(1),  "Freezer B"),
    ("Shrimp",             600, _exp(3),  "Freezer B"),

    # ── Vegetables (pcs) ─────────────────────────────────────────────────────
    ("Eggplant",             5, _exp(3),  "Shelf 1"),
    ("Eggplant",             6, _exp(6),  "Shelf 1"),
    ("Kangkong",             5, _exp(2),  "Shelf 1"),
    ("Kangkong",             6, _exp(4),  "Shelf 1"),
    ("Ampalaya",             4, _exp(3),  "Shelf 1"),
    ("Ampalaya",             5, _exp(7),  "Shelf 1"),
    ("Okra",                14, _exp(3),  "Shelf 1"),
    ("Okra",                18, _exp(6),  "Shelf 1"),
    ("Kalabasa",             2, _exp(5),  "Shelf 2"),
    ("Kalabasa",             3, _exp(10), "Shelf 2"),
    ("Pechay",               5, _exp(2),  "Shelf 1"),
    ("Pechay",               6, _exp(4),  "Shelf 1"),
    ("Sitaw",               18, _exp(3),  "Shelf 1"),   # total = 36pcs → Ginisang Sitaw=7
    ("Sitaw",               18, _exp(6),  "Shelf 1"),
    ("Onion",                7, _exp(10), "Shelf 3"),
    ("Onion",                8, _exp(20), "Shelf 3"),
    ("Onion",                7, _exp(30), "Shelf 3"),
    ("Garlic",              10, _exp(20), "Shelf 3"),
    ("Garlic",              12, _exp(35), "Shelf 3"),
    ("Garlic",              10, _exp(50), "Shelf 3"),
    ("Ginger",               5, _exp(10), "Shelf 3"),
    ("Ginger",               6, _exp(20), "Shelf 3"),
    ("Tomato",              10, _exp(3),  "Shelf 2"),
    ("Tomato",              12, _exp(6),  "Shelf 2"),
    ("Green Papaya",         2, _exp(5),  "Shelf 2"),
    ("Green Papaya",         3, _exp(12), "Shelf 2"),
    ("Carrot",               8, _exp(10), "Shelf 2"),
    ("Carrot",               8, _exp(20), "Shelf 2"),
    ("Bell Pepper",          5, _exp(5),  "Shelf 2"),
    ("Bell Pepper",          6, _exp(10), "Shelf 2"),
    ("Potato",              10, _exp(7),  "Shelf 2"),
    ("Potato",              12, _exp(15), "Shelf 2"),
    ("Bean Sprout",        400, _exp(3),  "Ref A"),        # g → Ukoy=8, Lumpiang Sariwa=13

    # ── Fruits (pcs) ─────────────────────────────────────────────────────────
    ("Banana",               6, _exp(2),  "Shelf 2"),
    ("Banana",               8, _exp(4),  "Shelf 2"),
    ("Banana",               7, _exp(7),  "Shelf 2"),
    ("Mango",                5, _exp(3),  "Shelf 2"),
    ("Mango",                6, _exp(6),  "Shelf 2"),
    ("Calamansi",           12, _exp(5),  "Shelf 2"),
    ("Calamansi",           15, _exp(12), "Shelf 2"),
    ("Green Mango",          4, _exp(5),  "Shelf 2"),      # total = 8pcs → Ensaladang Mangga=8
    ("Green Mango",          4, _exp(10), "Shelf 2"),
    ("Young Coconut",        2, _exp(3),  "Ref A"),   # total = 5pcs → Buko Pandan=20
    ("Young Coconut",        3, _exp(7),  "Ref A"),
    ("Lemon",                7, _exp(5),  "Shelf 2"),
    ("Lemon",                9, _exp(12), "Shelf 2"),

    # ── Condiments (pcs - bottles/cans) ──────────────────────────────────────
    # Cooking Oil (1L bottle)
    ("Cooking Oil",          2, _exp(300), "Pantry"),
    ("Cooking Oil",          2, _exp(365), "Pantry"),
    ("Cooking Oil",          2, _exp(400), "Pantry"),
    # Soy Sauce (750ml bottle)
    ("Soy Sauce",            2, _exp(300), "Pantry"),
    ("Soy Sauce",            2, _exp(365), "Pantry"),
    ("Soy Sauce",            2, _exp(400), "Pantry"),
    # Vinegar (750ml bottle)
    ("Vinegar",              2, _exp(600), "Pantry"),
    ("Vinegar",              3, _exp(730), "Pantry"),
    # Fish Sauce (700ml bottle)
    ("Fish Sauce",           1, _exp(300), "Pantry"),
    ("Fish Sauce",           2, _exp(365), "Pantry"),
    # Oyster Sauce (350ml bottle)
    ("Oyster Sauce",         1, _exp(150), "Pantry"),
    ("Oyster Sauce",         2, _exp(200), "Pantry"),
    # Sesame Oil (150ml bottle) - 1 batch
    ("Sesame Oil",           1, _exp(365), "Pantry"),
    # Tomato Paste (150g can)
    ("Tomato Paste",         2, _exp(150), "Pantry"),
    ("Tomato Paste",         2, _exp(200), "Pantry"),
    # Liver Spread (100g can)
    ("Liver Spread",         2, _exp(150), "Pantry"),
    ("Liver Spread",         2, _exp(200), "Pantry"),

    # ── Dry Goods ────────────────────────────────────────────────────────────
    ("Rice",              7000, _exp(150), "Pantry"),
    ("Rice",              7000, _exp(180), "Pantry"),
    ("Rice",              7000, _exp(210), "Pantry"),
    ("All-Purpose Flour",  800, _exp(150), "Pantry"),
    ("All-Purpose Flour", 1200, _exp(200), "Pantry"),
    ("Sugar",             1600, _exp(300), "Pantry"),
    ("Sugar",             1800, _exp(365), "Pantry"),
    ("Sugar",             1700, _exp(400), "Pantry"),
    ("Cornstarch",         250, _exp(300), "Pantry"),
    ("Cornstarch",         280, _exp(365), "Pantry"),
    ("Rice Flour",        1000, _exp(150), "Pantry"),
    ("Rice Flour",        1200, _exp(200), "Pantry"),
    ("Mung Bean",          250, _exp(300), "Pantry"),
    ("Mung Bean",          280, _exp(365), "Pantry"),
    ("Sago Pearl",         150, _exp(300), "Pantry"),
    ("Sago Pearl",         180, _exp(365), "Pantry"),
    ("Gulaman",            100, _exp(150), "Pantry"),
    ("Gulaman",            120, _exp(200), "Pantry"),
    ("Wonton Wrapper",      40, _exp(20),  "Pantry"),
    ("Wonton Wrapper",      45, _exp(45),  "Pantry"),
    ("Lumpia Wrapper",      40, _exp(20),  "Pantry"),
    ("Lumpia Wrapper",      45, _exp(45),  "Pantry"),

    # ── Dairy (pcs - cans/packs) - Coconut Milk absent → OUT OF STOCK ────────
    ("Egg",                 15, _exp(14),  "Ref A"),   # total = 35pcs → Leche Flan=8
    ("Egg",                 20, _exp(25),  "Ref A"),
    ("Evaporated Milk",      4, _exp(300), "Pantry"),
    ("Evaporated Milk",      4, _exp(365), "Pantry"),
    ("Condensed Milk",       2, _exp(300), "Pantry"),
    ("Condensed Milk",       2, _exp(365), "Pantry"),
    ("All-Purpose Cream",    1, _exp(20),  "Ref A"),
    ("All-Purpose Cream",    1, _exp(35),  "Ref A"),

    # ── Pantry ───────────────────────────────────────────────────────────────
    ("Salt",               650, _exp(600), "Pantry"),
    ("Salt",               700, _exp(680), "Pantry"),
    ("Salt",               700, _exp(730), "Pantry"),
    ("Black Pepper",       220, _exp(300), "Pantry"),
    ("Black Pepper",       280, _exp(365), "Pantry"),
    ("Bay Leaf",            25, _exp(150), "Pantry"),
    ("Bay Leaf",            30, _exp(200), "Pantry"),
    ("Tofu",                 3, _exp(5),   "Ref A"),
    ("Tofu",                 3, _exp(10),  "Ref A"),

    # ── Seasonings ───────────────────────────────────────────────────────────
    ("Annatto Powder",     100, _exp(150), "Pantry"),
    ("Annatto Powder",     120, _exp(200), "Pantry"),
    ("Bagoong Alamang",    250, _exp(75),  "Ref A"),
    ("Bagoong Alamang",    280, _exp(100), "Ref A"),
    ("Pandan Leaf",         10, _exp(5),   "Ref A"),
    ("Pandan Leaf",         12, _exp(10),  "Ref A"),
]


# ── RECIPES ───────────────────────────────────────────────────────────────────
# (name, category, serving_size, instructions, [(ingredient, qty_per_serving, unit), ...])
#
# Recipe ingredient units are always in usageUnit:
#   measurable products → ml, g, kg (recipe system converts from pcs via unitSize)
#   non-measurable (pcs) → pcs only
#
# Meat cuts changed:
#   Adobong Manok   : "Chicken" → "Chicken Thigh"
#   Tinolang Manok  : "Chicken" → "Chicken Wings"
#   Chicken Inasal  : "Chicken" → "Chicken Thigh"
#   Bulalo          : "Beef Brisket" → "Beef Shank"

SEED_RECIPES = [

    # ── APPETIZER (4) ────────────────────────────────────────────────────────

    ("Lumpia Shanghai", "Appetizer", 10,
     "1. Combine ground pork, onion, garlic, salt, and pepper in a bowl.\n"
     "2. Beat egg and fold into the filling.\n"
     "3. Place 1 tbsp of filling on a spring roll wrapper and roll tightly.\n"
     "4. Seal edges with a flour-water paste.\n"
     "5. Deep-fry in hot cooking oil until golden and crispy. Drain and serve.",
     [("Ground Pork", 100, "g"), ("Onion", 0.1, "pcs"), ("Garlic", 0.2, "pcs"),
      ("Egg", 0.1, "pcs"), ("All-Purpose Flour", 20, "g"),
      ("Salt", 2, "g"), ("Black Pepper", 1, "g"), ("Cooking Oil", 20, "ml")]),

    ("Siomai", "Appetizer", 8,
     "1. Mix ground pork, shrimp, carrot, onion, garlic, egg, cornstarch, "
     "sesame oil, oyster sauce, salt, and pepper until combined.\n"
     "2. Place 1 heaping teaspoon of filling in each wonton wrapper.\n"
     "3. Fold and pleat the edges to form a cup, leaving the top open.\n"
     "4. Arrange in a greased steamer basket.\n"
     "5. Steam over medium heat for 15-18 minutes. Serve with soy sauce and calamansi.",
     [("Ground Pork", 40, "g"), ("Shrimp", 20, "g"), ("Wonton Wrapper", 1, "pcs"),
      ("Onion", 0.1, "pcs"), ("Garlic", 0.3, "pcs"), ("Carrot", 0.1, "pcs"),
      ("Egg", 0.1, "pcs"), ("Cornstarch", 5, "g"), ("Sesame Oil", 1, "ml"),
      ("Oyster Sauce", 3, "ml"), ("Salt", 1, "g"), ("Black Pepper", 0.5, "g")]),

    ("Ukoy", "Appetizer", 4,
     "1. Whisk together flour, egg, salt, and enough water to make a thin batter.\n"
     "2. Add bean sprouts and minced garlic; mix well.\n"
     "3. Place whole shrimp on each fritter portion.\n"
     "4. Drop spoonfuls into hot cooking oil and press flat.\n"
     "5. Fry until golden and crispy on both sides. Serve with spiced vinegar.",
     [("Shrimp", 100, "g"), ("Bean Sprout", 50, "g"), ("All-Purpose Flour", 30, "g"),
      ("Egg", 0.25, "pcs"), ("Garlic", 0.5, "pcs"),
      ("Salt", 1, "g"), ("Cooking Oil", 20, "ml")]),

    ("Lumpiang Sariwa", "Appetizer", 8,
     "1. Sauté garlic and onion in cooking oil until soft.\n"
     "2. Add ground pork and cook until browned.\n"
     "3. Add shrimp, tofu, carrots, and bean sprouts; stir-fry 3 minutes.\n"
     "4. Season with fish sauce; cook until vegetables are tender. Cool.\n"
     "5. Wrap filling in lumpia wrapper and serve with sweet peanut sauce.",
     [("Lumpia Wrapper", 1, "pcs"), ("Ground Pork", 40, "g"), ("Shrimp", 25, "g"),
      ("Tofu", 0.1, "pcs"), ("Carrot", 0.1, "pcs"), ("Bean Sprout", 30, "g"),
      ("Onion", 0.1, "pcs"), ("Garlic", 0.3, "pcs"),
      ("Fish Sauce", 5, "ml"), ("Cooking Oil", 5, "ml")]),

    # ── MAIN COURSE (10) ─────────────────────────────────────────────────────

    ("Adobong Manok", "Main Course", 6,
     "1. Marinate chicken thigh in soy sauce, vinegar, garlic, and pepper for 30 min.\n"
     "2. Sear in cooking oil on both sides until lightly browned.\n"
     "3. Add marinade and bay leaves; bring to a boil.\n"
     "4. Lower heat and simmer 25 minutes until chicken is tender.\n"
     "5. Increase heat to reduce and glaze the sauce. Serve with steamed rice.",
     [("Chicken Thigh", 300, "g"), ("Soy Sauce", 40, "ml"), ("Vinegar", 20, "ml"),
      ("Garlic", 0.3, "pcs"), ("Bay Leaf", 0.3, "pcs"),
      ("Black Pepper", 2, "g"), ("Cooking Oil", 15, "ml")]),

    ("Kare-Kare", "Main Course", 5,
     "1. Simmer beef brisket in water until very tender, about 90 minutes.\n"
     "2. Sauté annatto powder in cooking oil; add to the broth for color.\n"
     "3. Stir in peanut butter or cornstarch paste to thicken the sauce.\n"
     "4. Add eggplant, okra, sitaw, and pechay; cook until just tender.\n"
     "5. Serve with bagoong alamang on the side.",
     [("Beef Brisket", 250, "g"), ("Eggplant", 1, "pcs"), ("Okra", 3, "pcs"),
      ("Sitaw", 3, "pcs"), ("Pechay", 1, "pcs"),
      ("Annatto Powder", 5, "g"), ("Bagoong Alamang", 30, "g"), ("Cooking Oil", 20, "ml")]),

    ("Lechon Kawali", "Main Course", 4,
     "1. Boil pork belly with garlic and salt until fork-tender, about 45 minutes.\n"
     "2. Pat completely dry; rub with salt. Refrigerate uncovered for 4 hours.\n"
     "3. Deep-fry in hot cooking oil, turning occasionally, until skin crackles.\n"
     "4. Drain on paper towels, then chop into serving pieces.\n"
     "5. Serve with lechon sauce or soy-vinegar dip.",
     [("Pork Belly", 250, "g"), ("Garlic", 0.3, "pcs"),
      ("Salt", 5, "g"), ("Black Pepper", 2, "g"), ("Cooking Oil", 50, "ml")]),

    ("Sinigang na Baboy", "Main Course", 6,
     "1. Boil pork belly in water until tender, about 40 minutes.\n"
     "2. Add onion and tomato; simmer 10 minutes.\n"
     "3. Stir in tamarind base or sinigang mix; season with fish sauce.\n"
     "4. Add okra and cook 5 minutes.\n"
     "5. Add kangkong last; cook 2 minutes. Serve hot with rice.",
     [("Pork Belly", 200, "g"), ("Tomato", 1, "pcs"), ("Onion", 0.5, "pcs"),
      ("Fish Sauce", 15, "ml"), ("Kangkong", 0.5, "pcs"), ("Okra", 3, "pcs")]),

    ("Bulalo", "Main Course", 4,
     "1. Blanch beef shank in boiling water for 5 minutes; rinse and clean.\n"
     "2. Simmer in fresh water with onion and garlic for 2-3 hours until very tender.\n"
     "3. Skim the broth periodically for clarity.\n"
     "4. Season with fish sauce and whole black pepper.\n"
     "5. Add pechay in the last 5 minutes. Serve hot.",
     [("Beef Shank", 250, "g"), ("Onion", 0.5, "pcs"), ("Garlic", 0.3, "pcs"),
      ("Fish Sauce", 15, "ml"), ("Pechay", 1, "pcs"), ("Black Pepper", 2, "g")]),

    ("Tinolang Manok", "Main Course", 5,
     "1. Sauté garlic, onion, and ginger in cooking oil until fragrant.\n"
     "2. Add chicken wings and cook until lightly browned on all sides.\n"
     "3. Pour in water or broth; bring to a boil then simmer 20 minutes.\n"
     "4. Add green papaya and cook 8 minutes until tender.\n"
     "5. Season with fish sauce; add pechay and cook 2 minutes. Serve hot.",
     [("Chicken Wings", 250, "g"), ("Ginger", 0.5, "pcs"), ("Onion", 0.5, "pcs"),
      ("Garlic", 0.3, "pcs"), ("Green Papaya", 0.5, "pcs"), ("Pechay", 1, "pcs"),
      ("Fish Sauce", 15, "ml"), ("Cooking Oil", 10, "ml")]),

    ("Caldereta", "Main Course", 6,
     "1. Brown beef brisket in cooking oil; set aside.\n"
     "2. Sauté garlic and onion; stir in tomato paste and liver spread.\n"
     "3. Return beef; add enough water to cover. Simmer 60 minutes.\n"
     "4. Add potato and bell pepper; cook 10 minutes until tender.\n"
     "5. Add bay leaves, season with salt and pepper. Serve hot with rice.",
     [("Beef Brisket", 200, "g"), ("Tomato", 0.5, "pcs"), ("Onion", 0.5, "pcs"),
      ("Garlic", 0.5, "pcs"), ("Bell Pepper", 0.25, "pcs"), ("Potato", 0.5, "pcs"),
      ("Tomato Paste", 15, "g"), ("Liver Spread", 10, "g"),
      ("Bay Leaf", 0.3, "pcs"), ("Salt", 2, "g"), ("Black Pepper", 1, "g"),
      ("Cooking Oil", 10, "ml")]),

    ("Ginataang Hipon Sitaw at Kalabasa", "Main Course", 4,
     "1. Sauté garlic and onion in cooking oil until fragrant.\n"
     "2. Add kalabasa pieces; cook 5 minutes until slightly softened.\n"
     "3. Pour in coconut milk and bring to a gentle simmer.\n"
     "4. Add sitaw and cook 3 minutes.\n"
     "5. Add shrimp, season with fish sauce, and cook 3 minutes until pink.",
     [("Shrimp", 150, "g"), ("Sitaw", 5, "pcs"), ("Kalabasa", 0.3, "pcs"),
      ("Coconut Milk", 60, "ml"), ("Garlic", 0.5, "pcs"), ("Onion", 0.5, "pcs"),
      ("Fish Sauce", 5, "ml"), ("Cooking Oil", 10, "ml")]),

    ("Chicken Inasal", "Main Course", 4,
     "1. Combine vinegar, garlic, ginger, annatto powder, fish sauce, and salt for marinade.\n"
     "2. Score the chicken thigh pieces and coat thoroughly; marinate at least 2 hours.\n"
     "3. Grill over medium-high heat, basting with annatto-oil mixture.\n"
     "4. Cook until skin is charred in spots and juices run clear.\n"
     "5. Serve with garlic rice and spiced vinegar.",
     [("Chicken Thigh", 250, "g"), ("Garlic", 1, "pcs"), ("Ginger", 0.5, "pcs"),
      ("Vinegar", 20, "ml"), ("Annatto Powder", 3, "g"),
      ("Fish Sauce", 10, "ml"), ("Salt", 2, "g"), ("Cooking Oil", 15, "ml")]),

    ("Kinilaw na Bangus", "Main Course", 4,
     "1. Fillet bangus and cut into bite-sized cubes; rinse in cold water.\n"
     "2. Marinate in vinegar for 5-8 minutes to cure the fish; drain excess liquid.\n"
     "3. Add ginger, onion, and calamansi juice; toss gently.\n"
     "4. Season with fish sauce and let sit 10 minutes to meld flavors.\n"
     "5. Adjust seasoning; serve chilled as a main course with rice.",
     [("Bangus", 200, "g"), ("Vinegar", 30, "ml"), ("Ginger", 1, "pcs"),
      ("Onion", 1, "pcs"), ("Calamansi", 3, "pcs"), ("Fish Sauce", 10, "ml")]),

    # ── SIDE DISH (5) ────────────────────────────────────────────────────────

    ("Ginisang Kangkong", "Side Dish", 3,
     "1. Heat cooking oil in a pan over medium heat.\n"
     "2. Sauté garlic until golden; add onion and cook until translucent.\n"
     "3. Add kangkong stalks first and cook 2 minutes.\n"
     "4. Add leaves, season with fish sauce, and toss quickly.\n"
     "5. Cook 1 more minute - do not overcook. Serve immediately.",
     [("Kangkong", 1, "pcs"), ("Garlic", 0.3, "pcs"), ("Onion", 0.3, "pcs"),
      ("Fish Sauce", 10, "ml"), ("Cooking Oil", 10, "ml")]),

    ("Ginisang Sitaw", "Side Dish", 4,
     "1. Heat oil; sauté garlic and onion until softened.\n"
     "2. Add tomato and cook 3 minutes until it breaks down.\n"
     "3. Add sitaw and stir-fry 5 minutes over high heat.\n"
     "4. Season with fish sauce; add a splash of water if needed.\n"
     "5. Cover and cook until beans are tender. Serve with rice.",
     [("Sitaw", 5, "pcs"), ("Garlic", 0.3, "pcs"), ("Onion", 0.3, "pcs"),
      ("Tomato", 0.5, "pcs"), ("Fish Sauce", 10, "ml"), ("Cooking Oil", 10, "ml")]),

    ("Ensaladang Talong", "Side Dish", 3,
     "1. Grill eggplants directly over flame until charred and very soft.\n"
     "2. Peel off the charred skin carefully; place flesh in a bowl.\n"
     "3. Flake the eggplant flesh and let cool completely.\n"
     "4. Mix with diced tomato and thinly sliced onion.\n"
     "5. Dress with fish sauce and calamansi juice. Serve at room temperature.",
     [("Eggplant", 1, "pcs"), ("Onion", 0.3, "pcs"), ("Tomato", 1, "pcs"),
      ("Fish Sauce", 10, "ml"), ("Calamansi", 2, "pcs")]),

    ("Ensaladang Mangga", "Side Dish", 3,
     "1. Peel and julienne green mango into thin strips.\n"
     "2. Dice tomato and thinly slice onion; combine with the mango.\n"
     "3. Mix in bagoong alamang and calamansi juice.\n"
     "4. Toss gently; refrigerate 10 minutes to meld flavors.\n"
     "5. Serve alongside grilled or fried fish.",
     [("Green Mango", 1, "pcs"), ("Tomato", 1, "pcs"), ("Onion", 0.3, "pcs"),
      ("Bagoong Alamang", 30, "g"), ("Calamansi", 2, "pcs")]),

    ("Ginisang Monggo", "Side Dish", 6,
     "1. Sauté garlic and onion in cooking oil; add tomato and cook until soft.\n"
     "2. Add ground pork and cook until no longer pink.\n"
     "3. Add pre-soaked mung beans and water to cover by 2 inches.\n"
     "4. Simmer 30-40 minutes, stirring occasionally, until beans are soft and creamy.\n"
     "5. Season with fish sauce; adjust consistency with water. Serve hot.",
     [("Mung Bean", 30, "g"), ("Ground Pork", 30, "g"), ("Garlic", 0.3, "pcs"),
      ("Onion", 0.3, "pcs"), ("Tomato", 0.5, "pcs"),
      ("Fish Sauce", 5, "ml"), ("Cooking Oil", 5, "ml")]),

    # ── DESSERT (5) ──────────────────────────────────────────────────────────

    ("Leche Flan", "Dessert", 6,
     "1. Caramelize sugar in a llanera mold over low heat until amber; swirl to coat.\n"
     "2. Beat egg yolks with evaporated milk, condensed milk, and a squeeze of calamansi.\n"
     "3. Strain the custard into the caramelized mold.\n"
     "4. Cover with foil and steam over low heat 30-35 minutes until set.\n"
     "5. Cool completely, then invert onto a plate. Serve chilled.",
     [("Egg", 4, "pcs"), ("Evaporated Milk", 100, "ml"), ("Condensed Milk", 50, "ml"),
      ("Sugar", 80, "g"), ("Calamansi", 0.3, "pcs")]),

    ("Bibingka", "Dessert", 4,
     "1. Mix rice flour, sugar, and a pinch of salt.\n"
     "2. Add beaten eggs, coconut milk, and evaporated milk; stir until smooth.\n"
     "3. Line clay or muffin molds with banana leaf; pour batter in.\n"
     "4. Bake at 200°C for 20-25 minutes until golden on top and set in center.\n"
     "5. Brush with butter and top with salted egg. Serve warm.",
     [("Rice Flour", 100, "g"), ("Egg", 2, "pcs"), ("Coconut Milk", 120, "ml"),
      ("Evaporated Milk", 30, "ml"), ("Sugar", 50, "g"), ("Salt", 2, "g")]),

    ("Maja Blanca", "Dessert", 8,
     "1. Whisk coconut milk, cornstarch, and sugar together in a heavy saucepan.\n"
     "2. Cook over medium heat, stirring constantly, until the mixture thickens.\n"
     "3. Add evaporated milk halfway; continue stirring until it pulls away from the sides.\n"
     "4. Pour into a lightly oiled dish and smooth the top.\n"
     "5. Cool to room temperature, refrigerate until firm. Top with latik and serve.",
     [("Coconut Milk", 200, "ml"), ("Cornstarch", 40, "g"),
      ("Sugar", 60, "g"), ("Evaporated Milk", 50, "ml")]),

    ("Turon", "Dessert", 8,
     "1. Peel bananas and roll each one in sugar to coat.\n"
     "2. Place a sugared banana in the center of a lumpia wrapper.\n"
     "3. Fold the sides in and roll up tightly, sealing the edge with a little water.\n"
     "4. Heat cooking oil over medium heat; fry turon until golden and caramelized.\n"
     "5. Drain on paper towels. Serve warm.",
     [("Banana", 1, "pcs"), ("Lumpia Wrapper", 1, "pcs"),
      ("Sugar", 10, "g"), ("Cooking Oil", 15, "ml")]),

    ("Buko Pandan", "Dessert", 8,
     "1. Boil pandan leaves in water 10 minutes; strain and reserve pandan water.\n"
     "2. Dissolve gulaman in pandan water; boil, cool, then cut into small cubes.\n"
     "3. Cook sago pearls until translucent; drain and rinse.\n"
     "4. Scoop young coconut flesh into strips; reserve coconut water.\n"
     "5. Mix coconut flesh, gulaman, sago, condensed milk, all-purpose cream, "
     "and coconut water. Chill and serve cold.",
     [("Young Coconut", 0.25, "pcs"), ("Pandan Leaf", 0.5, "pcs"),
      ("Gulaman", 5, "g"), ("Sago Pearl", 5, "g"),
      ("Condensed Milk", 25, "ml"), ("All-Purpose Cream", 15, "ml"),
      ("Sugar", 10, "g")]),
]


# ── PREPARATIONS (production history, last 30 days) ──────────────────────────

SEED_PREPARATIONS = [
    (30, "Adobong Manok",          8),
    (29, "Sinigang na Baboy",      6),
    (28, "Ginisang Kangkong",      4),
    (28, "Lechon Kawali",          5),
    (27, "Adobong Manok",          6),
    (26, "Tinolang Manok",         7),
    (25, "Ginisang Monggo",        5),
    (24, "Adobong Manok",          8),
    (23, "Sinigang na Baboy",      6),
    (22, "Ginisang Sitaw",         4),
    (22, "Kare-Kare",              4),
    (21, "Ginisang Kangkong",      6),
    (20, "Lechon Kawali",          4),
    (19, "Adobong Manok",          7),
    (17, "Tinolang Manok",         6),
    (16, "Sinigang na Baboy",      8),
    (15, "Adobong Manok",          8),
    (14, "Ginisang Monggo",        4),
    (13, "Ginisang Kangkong",      5),
    (13, "Lechon Kawali",          6),
    (10, "Adobong Manok",         10),
    (9,  "Sinigang na Baboy",      6),
    (8,  "Tinolang Manok",         7),
    (7,  "Kare-Kare",              5),
    (6,  "Ginisang Kangkong",      4),
    (5,  "Adobong Manok",          8),
    (4,  "Lechon Kawali",          5),
    (3,  "Ginisang Monggo",        6),
    (2,  "Sinigang na Baboy",      8),
    (1,  "Adobong Manok",          6),
]


# ── USED STOCK ────────────────────────────────────────────────────────────────
# Simulates a kitchen that has been operating: some bottles/cans are partially used.
# (product_name, remainingBase, baseUnit)
#   remainingBase = how much is left in opened units, in ml or g
SEED_USED_STOCK = [
    # Condiments
    ("Cooking Oil",   970, "ml"),  # 1000ml bottle, used 30ml
    ("Fish Sauce",    420, "ml"),  # 700ml bottle, used 280ml
    ("Soy Sauce",     280, "ml"),  # 750ml bottle, used 470ml
    ("Oyster Sauce",  175, "ml"),  # 350ml bottle, used 175ml
    ("Sesame Oil",     80, "ml"),  # 150ml bottle, used 70ml
    ("Vinegar",       550, "ml"),  # 750ml bottle, used 200ml
    ("Liver Spread",   45, "g"),   # 100g can, used 55g
    # Tomato Paste: can is fully used - no entry (0 remaining)

    # Dairy
    ("All-Purpose Cream", 150, "ml"),  # 250ml pack, used 100ml
    ("Condensed Milk",    200, "ml"),  # 390ml can, used 190ml
    ("Evaporated Milk",   185, "ml"),  # 370ml can, used 185ml
    # Coconut Milk: out of stock - no entry
]


# ── MAIN ──────────────────────────────────────────────────────────────────────

def slug(name):
    return (name.strip().lower()
            .replace(" ", "_").replace("/", "_")
            .replace("'", "").replace("(", "").replace(")", ""))


def main():
    db = get_db()

    # ── 0. Cleanup: delete legacy "Fresh Produce" products ───────────────────
    print("\n=== CLEANUP: Fresh Produce duplicates ===")
    fresh_produce_docs = list(db.collection("products").where("category", "==", "Fresh Produce").stream())
    if not fresh_produce_docs:
        print("  Nothing to clean up.")
    for doc in fresh_produce_docs:
        name = doc.to_dict().get("name", doc.id)
        print(f"  {'DELETE' if COMMIT else 'DRY'}  products/{doc.id}  (name={name})")
        if COMMIT:
            doc.reference.delete()

    # ── 1. Firebase Auth + Firestore users ───────────────────────────────────
    print("\n=== USERS ===")
    uid_map: dict[str, str] = {}

    for u in SEED_USERS:
        email = u["email"]
        try:
            existing = fb_auth.get_user_by_email(email)
            uid = existing.uid
            print(f"  auth EXISTS  {email}  (uid={uid})")
        except fb_auth.UserNotFoundError:
            if COMMIT:
                record = fb_auth.create_user(
                    email=email,
                    password=u["password"],
                    display_name=u["fullName"],
                )
                uid = record.uid
                print(f"  auth CREATED {email}  (uid={uid})")
            else:
                uid = f"DRY_seed_{slug(email.split('@')[0])}"
                print(f"  auth DRY-RUN {email}")

        uid_map[email] = uid

        profile = {
            "uid": uid,
            "email": email,
            "fullName": u["fullName"],
            "role": u["role"],
            "phoneNumber": "",
            "unitPreference": "Metric (g/ml)",
            "isActive": True,
            "shiftOn": False,
            "isArchived": False,
            "permissions": u["permissions"],
            "photoUrl": "",
            "createdAt": fb_fs.SERVER_TIMESTAMP,
        }
        if COMMIT:
            db.collection("users").document(uid).set(profile, merge=True)
            print(f"  firestore SET users/{uid}  role={u['role']}")
        else:
            print(f"  firestore DRY users/{uid}  role={u['role']}")

    admin_uid = uid_map.get("admin@gmail.com", "seed_admin")
    admin_name = "Smith Doe"
    admin_role = "admin"

    # ── 2. Products ──────────────────────────────────────────────────────────
    print("\n=== PRODUCTS ===")
    product_id_map: dict[str, str] = {}

    for (name, category, du, min_thresh, shelf_days, measurable, unit_size, usage_unit) in SEED_PRODUCTS:
        doc_id = f"seed_{slug(name)}"
        bu = base_unit(du)
        data = {
            "name": name,
            "category": category,
            "baseUnit": bu,
            "displayUnit": du,
            "minimumThreshold": to_base(min_thresh, du),
            "shelfLifeDays": shelf_days,
            "barcode": "",
            "countable": bu == "piece",
            "measurable": measurable,
            "unitSize": unit_size,
            "usageUnit": usage_unit,
            "createdAt": fb_fs.SERVER_TIMESTAMP,
            "updatedAt": fb_fs.SERVER_TIMESTAMP,
        }
        product_id_map[name] = doc_id
        if COMMIT:
            db.collection("products").document(doc_id).set(data, merge=True)
        m = f"measurable({usage_unit}, ×{unit_size})" if measurable else "not-measurable"
        print(f"  {'SET' if COMMIT else 'DRY'}  products/{doc_id}  [{category}] {du}  {m}")

    # ── 3. Inventory batches ─────────────────────────────────────────────────
    print("\n=== INVENTORY BATCHES ===")
    batch_counter: dict[str, int] = {}

    for (name, qty_base, expiry_dt, location) in SEED_BATCHES:
        batch_counter[name] = batch_counter.get(name, 0) + 1
        pid = product_id_map.get(name, f"seed_{slug(name)}")
        doc_id = f"seed_batch_{slug(name)}_{batch_counter[name]}"
        data = {
            "productId": pid,
            "quantity": qty_base,
            "expirationDate": expiry_dt,
            "receivedDate": fb_fs.SERVER_TIMESTAMP,
            "location": location,
            "source": "seeder",
            "addedBy": admin_name,
        }
        if COMMIT:
            db.collection("inventory_batches").document(doc_id).set(data, merge=True)
        print(f"  {'SET' if COMMIT else 'DRY'}  inventory_batches/{doc_id}  qty={qty_base}  exp={expiry_dt.date()}")

    print("  NOTE: Coconut Milk has no batch → OUT OF STOCK (Bibingka, Maja Blanca, Ginataang Hipon = 0)")

    # ── 4. Recipes ───────────────────────────────────────────────────────────
    print("\n=== RECIPES ===")
    recipe_map: dict[str, str] = {}

    for (name, category, serving_size, instructions, ingredients) in SEED_RECIPES:
        doc_id = f"seed_{slug(name)}"
        recipe_map[name] = doc_id
        ings = [{"name": n, "quantity": q, "unit": u, "productId": None} for n, q, u in ingredients]
        data = {
            "name": name,
            "category": category,
            "servingSize": serving_size,
            "instructions": instructions,
            "ingredients": ings,
            "createdBy": admin_uid,
            "createdAt": fb_fs.SERVER_TIMESTAMP,
            "updatedAt": fb_fs.SERVER_TIMESTAMP,
        }
        if COMMIT:
            db.collection("recipes").document(doc_id).set(data, merge=True)
        print(f"  {'SET' if COMMIT else 'DRY'}  recipes/{doc_id}  [{category}]  {len(ings)} ingredients")

    # ── 5. Preparations ──────────────────────────────────────────────────────
    print("\n=== PREPARATIONS ===")
    recipe_category_map = {name: cat for name, cat, *_ in SEED_RECIPES}

    for i, (days_ago, recipe_name, servings) in enumerate(SEED_PREPARATIONS):
        prep_date = TODAY - datetime.timedelta(days=days_ago)
        doc_id = f"seed_prep_{i:03d}"
        rid = recipe_map.get(recipe_name, f"seed_{slug(recipe_name)}")
        cat = recipe_category_map.get(recipe_name, "Main Course")
        data = {
            "recipeId": rid,
            "recipeName": recipe_name,
            "category": cat,
            "servings": servings,
            "preparedBy": admin_uid,
            "preparedByName": admin_name,
            "preparedByRole": admin_role,
            "consumed": [],
            "preparedAt": ts(prep_date),
            "date": prep_date.isoformat(),
        }
        if COMMIT:
            db.collection("preparations").document(doc_id).set(data, merge=True)
        print(f"  {'SET' if COMMIT else 'DRY'}  preparations/{doc_id}  {prep_date}  {recipe_name} ×{servings}")

    # ── 6. Used stock ────────────────────────────────────────────────────────
    print("\n=== USED STOCK ===")
    for (name, remaining_base, base_unit_str) in SEED_USED_STOCK:
        pid = product_id_map.get(name, f"seed_{slug(name)}")
        data = {
            "remainingBase": remaining_base,
            "updatedAt": fb_fs.SERVER_TIMESTAMP,
        }
        if COMMIT:
            db.collection("used_stock").document(pid).set(data, merge=True)
        print(f"  {'SET' if COMMIT else 'DRY'}  used_stock/{pid}  {remaining_base}{base_unit_str} remaining")

    # ── Summary ───────────────────────────────────────────────────────────────
    cats = {}
    for _, cat, *_ in SEED_RECIPES:
        cats[cat] = cats.get(cat, 0) + 1
    cat_summary = ", ".join(f"{k}: {v}" for k, v in sorted(cats.items()))

    print("\n── EXPECTED CAN-COOK HIGHLIGHTS ──────────────────────────────────")
    print("  Adobong Manok          : ~10  (3000 g chicken thigh ÷ 300 g)")
    print("  Chicken Inasal         : ~12  (3000 g chicken thigh ÷ 250 g)")
    print("  Tinolang Manok         :  ~8  (2000 g chicken wings ÷ 250 g)")
    print("  Sinigang na Baboy      : ~10  (okra 36pcs ÷ 3 limits; pork belly ample)")
    print("  Lechon Kawali          : ~18  (4500 g pork belly ÷ 250 g)")
    print("  Caldereta              : ~12  (2500 g beef brisket ÷ 200 g)")
    print("  Kare-Kare              : ~10  (2500 g beef brisket ÷ 250 g)")
    print("  Bulalo                 :  ~8  (2000 g beef shank ÷ 250 g)")
    print("  Kinilaw na Bangus      :  ~8  (1600 g bangus ÷ 200 g)")
    print("  Lumpia Shanghai        :  ~9  (900 g ground pork ÷ 100 g)")
    print("  Ukoy                   :  ~8  (400 g bean sprout ÷ 50 g)")
    print("  Leche Flan             :  ~8  (35 pcs egg ÷ 4 pcs)")
    print("  Ensaladang Mangga      :  ~8  (8 pcs green mango ÷ 1 pcs)")
    print("  Buko Pandan            : ~20  (5 pcs young coconut ÷ 0.25 pcs)")
    print("  Bibingka               :   0  (Coconut Milk OUT)               ← CANNOT COOK")
    print("  Maja Blanca            :   0  (Coconut Milk OUT)               ← CANNOT COOK")
    print("  Ginataang Hipon        :   0  (Coconut Milk OUT)               ← CANNOT COOK")

    measurable_count = sum(1 for *_, m, _, _ in SEED_PRODUCTS if m)
    not_measurable_count = len(SEED_PRODUCTS) - measurable_count

    if not COMMIT:
        print("\n── DRY RUN - no writes. Re-run with --commit to apply. ──────────")
    else:
        print(f"\n── DONE: {len(SEED_USERS)} users, {len(SEED_PRODUCTS)} products "
              f"({measurable_count} measurable, {not_measurable_count} not-measurable), "
              f"{len(SEED_BATCHES)} batches, {len(SEED_RECIPES)} recipes ({cat_summary}), "
              f"{len(SEED_PREPARATIONS)} preparations, {len(SEED_USED_STOCK)} used_stock entries. ──")


if __name__ == "__main__":
    main()
