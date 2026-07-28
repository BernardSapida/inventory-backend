"""
Full seed: Firebase Auth users, Firestore users, products, inventory_batches,
recipes, and preparations (production history).

Dataset: Italian restaurant (pizzeria + pasta kitchen + wine list).
Source of truth for the menu and ingredients: data/recipe-and-products.md
  - 25 pizzas + 25 pasta dishes = 50 recipes
  - 20 Italian wines stocked as Beverages
  - Ingredient names below MUST match the recipe ingredient names exactly;
    the apps match a recipe ingredient to a product by name (case-insensitive).

Design goals:
  - measurable=True  → item can be used in different units (ml, g, L, tbsp…)
                       needs unitSize (how many usageUnits per 1 purchaseUnit)
  - measurable=False → item is always in pcs (egg, dough ball, onion, sage leaf…)
  - Sauces, oils, broths, cream and wine tracked in pcs (bottles/jars/cartons),
    usageUnit for recipes = ml or g
  - Pizzas: servingSize 1 = one whole pizza, quantities are per pizza
  - Pasta:  servingSize 4 (or 6 for the baked dishes), quantities are per plate
  - used_stock collection seeded with realistic partial-bottle/jar values
  - Buffalo Mozzarella has no batch → OUT OF STOCK (Pizza Bufalina = 0)
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


# Density (g/ml) by product name - MIRRORS DENSITY_DEFAULTS in
# smartstock-admin/src/lib/units.ts and inventory-native/lib/types/product.ts.
# Lets a mass-stocked seasoning be measured in tbsp/tsp (1 tbsp butter = 13.5 g).
# Keep these three tables in sync. Only g-based products carry a density.
import re

_DENSITY_DEFAULTS = [
    (r"\b(brown\s+sugar)\b", 0.93),
    (r"\b(powdered|icing|confectioner'?s)\s+sugar\b", 0.56),
    (r"\bsugar\b", 0.845),
    (r"\b(table\s+)?salt\b", 1.2),
    (r"\b(baking\s+(soda|powder))\b", 0.9),
    (r"\b(corn\s*starch|cornflour)\b", 0.63),
    (r"\bflour\b", 0.53),
    (r"\b(pepper|paprika|cumin|cinnamon|turmeric|oregano|chili\s*powder|spice|seasoning)\b", 0.5),
    (r"\b(msg|vetsin|monosodium)\b", 0.92),
    (r"\b(rice)\b", 0.85),
    (r"\b(oil|vinegar|soy\s*sauce|fish\s*sauce|water|milk|broth|stock)\b", 1.0),
    (r"\b(honey|syrup|molasses)\b", 1.42),
    (r"\b(butter|margarine)\b", 0.91),
]


def suggested_density(name, du):
    """Name-matched density (g/ml), or None. Only meaningful for g-based stock."""
    if base_unit(du) != "g":
        return None
    n = name.strip().lower()
    for pattern, value in _DENSITY_DEFAULTS:
        if re.search(pattern, n):
            return value
    return None


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
        "fullName": "Marco Rossi",
        "role": "admin",
        "permissions": _ADMIN_PERMS,
    },
    {
        "email": "staff@gmail.com",
        "password": "@Password123",
        "fullName": "Giulia Bianchi",
        "role": "staff",
        "permissions": _STAFF_PERMS,
    },
]


# ── PRODUCTS ──────────────────────────────────────────────────────────────────
# (name, category, displayUnit, minThresholdDisplay, shelfLifeDays, measurable, unitSize, usageUnit)
#
# measurable=True  → item can be measured in different units in recipes
#                    unitSize = how many usageUnits are in 1 displayUnit
#                    e.g. 1 bottle Olive Oil = 1000ml → unitSize=1000, usageUnit="ml"
#                    e.g. 1 kg Guanciale     = 1000g  → unitSize=1000, usageUnit="g"
# measurable=False → item is always pcs in recipes (egg, dough, onion, sage leaf…)
#                    unitSize=None, usageUnit="pcs"

SEED_PRODUCTS = [

    # ── Bakery ────────────────────────────────────────────────────────────────
    ("Pizza Dough",              "Bakery", "pcs", 15,   3, False, None, "pcs"),

    # ── Meat (Italian cured meats + butchery) ─────────────────────────────────
    ("Guanciale",                "Meat", "kg", 0.5,  21, True, 1000, "g"),
    ("Pancetta",                 "Meat", "kg", 0.5,  14, True, 1000, "g"),
    ("Parma Ham",                "Meat", "kg", 0.3,  14, True, 1000, "g"),
    ("Prosciutto",               "Meat", "kg", 0.3,  14, True, 1000, "g"),
    ("Cooked Ham",               "Meat", "kg", 0.5,  10, True, 1000, "g"),
    ("Salami",                   "Meat", "kg", 0.5,  30, True, 1000, "g"),
    ("Spicy Calabrese Salami",   "Meat", "kg", 0.5,  30, True, 1000, "g"),
    ("Italian Sausage",          "Meat", "kg", 1.0,   5, True, 1000, "g"),
    ("Spicy Italian Sausage",    "Meat", "kg", 0.5,   5, True, 1000, "g"),
    ("Ground Beef",              "Meat", "kg", 2.0,   3, True, 1000, "g"),
    ("Wild Boar Meat",           "Meat", "kg", 1.0,   3, True, 1000, "g"),

    # ── Seafood ───────────────────────────────────────────────────────────────
    ("Shrimp",                   "Seafood", "kg",  0.5,   2, True, 1000, "g"),
    ("Squid Rings",              "Seafood", "kg",  0.5,   2, True, 1000, "g"),
    ("Mussels",                  "Seafood", "kg",  1.0,   2, True, 1000, "g"),
    ("Clams",                    "Seafood", "kg",  1.0,   2, True, 1000, "g"),
    ("Anchovy Fillets",          "Seafood", "pcs", 30,  180, False, None, "pcs"),
    ("Canned Tuna",              "Seafood", "pcs",  4,  540, True,  160, "g"),   # 160g can

    # ── Dairy (the cheese wall) ───────────────────────────────────────────────
    ("Fresh Mozzarella",         "Dairy", "kg",  1.0,   7, True, 1000, "g"),
    ("Shredded Mozzarella",      "Dairy", "kg",  2.0,  14, True, 1000, "g"),
    ("Buffalo Mozzarella",       "Dairy", "kg",  0.5,   5, True, 1000, "g"),   # NO BATCH
    ("Ricotta Cheese",           "Dairy", "kg",  0.5,   7, True, 1000, "g"),
    ("Ricotta Salata",           "Dairy", "kg",  0.3,  30, True, 1000, "g"),
    ("Parmesan Cheese",          "Dairy", "kg",  0.5,  90, True, 1000, "g"),
    ("Pecorino Romano",          "Dairy", "kg",  0.5,  90, True, 1000, "g"),
    ("Gorgonzola Cheese",        "Dairy", "kg",  0.3,  21, True, 1000, "g"),
    ("Fontina Cheese",           "Dairy", "kg",  0.3,  30, True, 1000, "g"),
    ("Heavy Cream",              "Dairy", "pcs", 2,    14, True, 1000, "ml"),  # 1L carton
    ("Butter",                   "Dairy", "kg",  0.5,  60, True, 1000, "g"),   # density 0.91 → tbsp
    ("Egg",                      "Dairy", "pcs", 24,   21, False, None, "pcs"),

    # ── Vegetables (fresh produce) ────────────────────────────────────────────
    ("Garlic",                   "Vegetables", "pcs", 30,  30, False, None, "pcs"),  # cloves
    ("Yellow Onion",             "Vegetables", "pcs", 10,  30, False, None, "pcs"),
    ("Red Onion",                "Vegetables", "pcs",  8,  30, False, None, "pcs"),
    ("Carrot",                   "Vegetables", "pcs", 10,  21, False, None, "pcs"),
    ("Celery",                   "Vegetables", "pcs",  8,  14, False, None, "pcs"),  # stalks
    ("Zucchini",                 "Vegetables", "pcs",  6,  10, False, None, "pcs"),
    ("Eggplant",                 "Vegetables", "pcs",  5,  10, False, None, "pcs"),
    ("Bell Pepper",              "Vegetables", "pcs",  6,  12, False, None, "pcs"),
    ("Fresh Tomatoes",           "Vegetables", "pcs", 10,   7, False, None, "pcs"),
    ("Cherry Tomatoes",          "Vegetables", "g",  300,   7, True,  1,    "g"),
    ("Mushrooms",                "Vegetables", "g",  500,   7, True,  1,    "g"),
    ("Spinach",                  "Vegetables", "g",  300,   5, True,  1,    "g"),
    ("Broccoli Rabe",            "Vegetables", "g",  300,   4, True,  1,    "g"),
    ("Arugula",                  "Vegetables", "g",  200,   4, True,  1,    "g"),

    # ── Seasonings (fresh herbs + dried) ──────────────────────────────────────
    ("Fresh Basil",              "Seasonings", "g",   80,   4, True,  1,    "g"),
    ("Fresh Parsley",            "Seasonings", "g",   80,   5, True,  1,    "g"),
    ("Fresh Rosemary",           "Seasonings", "g",   50,   7, True,  1,    "g"),
    ("Fresh Sage",               "Seasonings", "pcs", 20,   7, False, None, "pcs"),  # leaves
    ("Oregano",                  "Seasonings", "g",   50, 365, True,  1,    "g"),
    ("Chili Flakes",             "Seasonings", "g",   50, 365, True,  1,    "g"),
    ("Italian Seasoning",        "Seasonings", "g",   50, 365, True,  1,    "g"),
    ("Fennel Seeds",             "Seasonings", "g",   40, 365, True,  1,    "g"),
    ("Black Pepper",             "Seasonings", "g",   60, 365, True,  1,    "g"),   # density 0.5 → tsp
    ("Salt",                     "Seasonings", "g",  300, 730, True,  1,    "g"),

    # ── Condiments (oils) ─────────────────────────────────────────────────────
    ("Olive Oil",                "Condiments", "pcs", 3, 540, True, 1000, "ml"),  # 1L bottle
    ("Truffle Oil",              "Condiments", "pcs", 1, 365, True,  100, "ml"),  # 100ml bottle

    # ── Pantry (cans, jars, sauces, broths) ───────────────────────────────────
    ("Crushed Tomatoes",         "Pantry", "pcs", 12, 540, True,  400, "g"),   # 400g can
    ("Tomato Sauce",             "Pantry", "pcs",  6, 365, True,  700, "ml"),  # 700ml jar
    ("Marinara Sauce",           "Pantry", "pcs",  4, 365, True,  700, "ml"),  # 700ml jar
    ("Tomato Paste",             "Pantry", "pcs",  6, 365, True,  150, "g"),   # 150g tube
    ("Bechamel Sauce",           "Pantry", "pcs",  4,  30, True,  500, "ml"),  # 500ml pack
    ("Basil Pesto",              "Pantry", "pcs",  4, 180, True,  190, "g"),   # 190g jar
    ("Cannellini Beans",         "Pantry", "pcs",  6, 540, True,  400, "g"),   # 400g can
    ("Artichoke Hearts",         "Pantry", "g",  300, 180, True,  1,    "g"),
    ("Black Olives",             "Pantry", "g",  300, 180, True,  1,    "g"),
    ("Capers",                   "Pantry", "g",  150, 365, True,  1,    "g"),
    ("Sweet Corn",               "Pantry", "g",  300, 365, True,  1,    "g"),
    ("Pine Nuts",                "Pantry", "g",  150, 180, True,  1,    "g"),
    ("Breadcrumbs",              "Pantry", "g",  250, 180, True,  1,    "g"),
    ("Chicken Broth",            "Pantry", "pcs",  4, 365, True, 1000, "ml"),  # 1L carton
    ("Beef Broth",               "Pantry", "pcs",  4, 365, True, 1000, "ml"),
    ("Vegetable Broth",          "Pantry", "pcs",  4, 365, True, 1000, "ml"),

    # ── Dry Goods (dry pasta) ─────────────────────────────────────────────────
    ("Spaghetti",                "Dry Goods", "kg",  3, 540, True, 1000, "g"),
    ("Penne",                    "Dry Goods", "kg",  3, 540, True, 1000, "g"),
    ("Fettuccine",               "Dry Goods", "kg",  2, 540, True, 1000, "g"),
    ("Tagliatelle",              "Dry Goods", "kg",  2, 540, True, 1000, "g"),
    ("Linguine",                 "Dry Goods", "kg",  2, 540, True, 1000, "g"),
    ("Bucatini",                 "Dry Goods", "kg",  2, 540, True, 1000, "g"),
    ("Tonnarelli",               "Dry Goods", "kg",  1, 540, True, 1000, "g"),
    ("Orecchiette",              "Dry Goods", "kg",  1, 540, True, 1000, "g"),
    ("Pappardelle",              "Dry Goods", "kg",  1, 540, True, 1000, "g"),
    ("Trofie",                   "Dry Goods", "kg",  1, 540, True, 1000, "g"),
    ("Rigatoni",                 "Dry Goods", "kg",  2, 540, True, 1000, "g"),
    ("Ditalini",                 "Dry Goods", "kg",  1, 540, True, 1000, "g"),
    ("Elbow Macaroni",           "Dry Goods", "kg",  1, 540, True, 1000, "g"),
    ("Lasagne Sheets",           "Dry Goods", "pcs", 24, 540, False, None, "pcs"),
    ("Cannelloni Tubes",         "Dry Goods", "pcs", 24, 540, False, None, "pcs"),
    ("Manicotti Shells",         "Dry Goods", "pcs", 16, 540, False, None, "pcs"),

    # ── Frozen (fresh filled pasta, held frozen) ──────────────────────────────
    ("Tortellini",               "Frozen", "kg", 1, 90, True, 1000, "g"),
    ("Spinach & Ricotta Ravioli", "Frozen", "kg", 1, 90, True, 1000, "g"),
    ("Potato Gnocchi",           "Frozen", "kg", 1, 90, True, 1000, "g"),

    # ── Beverages: kitchen alcohol ────────────────────────────────────────────
    ("Dry White Wine",           "Beverages", "pcs", 3,  730, True, 750, "ml"),
    ("Red Wine",                 "Beverages", "pcs", 3,  730, True, 750, "ml"),
    ("Vodka",                    "Beverages", "pcs", 1, 1825, True, 700, "ml"),

    # ── Beverages: the wine list (750ml bottles, sold by bottle/glass) ────────
    ("Chianti",                     "Beverages", "pcs", 6, 1825, True, 750, "ml"),
    ("Barolo",                      "Beverages", "pcs", 4, 1825, True, 750, "ml"),
    ("Barbaresco",                  "Beverages", "pcs", 4, 1825, True, 750, "ml"),
    ("Brunello di Montalcino",      "Beverages", "pcs", 4, 1825, True, 750, "ml"),
    ("Amarone della Valpolicella",  "Beverages", "pcs", 4, 1825, True, 750, "ml"),
    ("Montepulciano d'Abruzzo",     "Beverages", "pcs", 6, 1460, True, 750, "ml"),
    ("Nero d'Avola",                "Beverages", "pcs", 6, 1460, True, 750, "ml"),
    ("Primitivo",                   "Beverages", "pcs", 6, 1460, True, 750, "ml"),
    ("Valpolicella Classico",       "Beverages", "pcs", 6, 1095, True, 750, "ml"),
    ("Lambrusco",                   "Beverages", "pcs", 6,  730, True, 750, "ml"),
    ("Pinot Grigio",                "Beverages", "pcs", 8,  730, True, 750, "ml"),
    ("Soave",                       "Beverages", "pcs", 6,  730, True, 750, "ml"),
    ("Verdicchio",                  "Beverages", "pcs", 6,  730, True, 750, "ml"),
    ("Gavi",                        "Beverages", "pcs", 6,  730, True, 750, "ml"),
    ("Vermentino",                  "Beverages", "pcs", 6,  730, True, 750, "ml"),
    ("Prosecco",                    "Beverages", "pcs", 8,  730, True, 750, "ml"),
    ("Franciacorta",                "Beverages", "pcs", 4,  730, True, 750, "ml"),
    ("Asti Spumante",               "Beverages", "pcs", 4,  730, True, 750, "ml"),
    ("Moscato d'Asti",              "Beverages", "pcs", 4,  730, True, 750, "ml"),
    ("Vin Santo",                   "Beverages", "pcs", 3, 1825, True, 750, "ml"),
]


# ── INVENTORY BATCHES ─────────────────────────────────────────────────────────
# (product_name, quantity_in_base_units, expiry_date, location)
# kg products  : quantity in grams
# g products   : quantity in grams
# pcs products : quantity in pieces (bottles/cans/jars/dough balls)
#
# Intentional shortages, so the alerts and "can cook" counts have something to say:
#   Buffalo Mozzarella  (no batch)   → Pizza Bufalina        = 0   ← OUT OF STOCK
#   Wild Boar Meat      800 g        → Pappardelle Cinghiale = 6   ← LOW
#   Clams               1200 g       → Spaghetti Vongole     = 4   ← LOW
#   Truffle Oil         1 bottle     → Pizza Tartufata       = 10  ← LOW
#   Ricotta Salata      300 g        → Pasta alla Norma      = 12  ← LOW
#   Pizza Dough         26 pcs, 1-3 days out                       ← EXPIRING

def _exp(n):
    return ts(TODAY + datetime.timedelta(days=n))


SEED_BATCHES = [

    # ── Bakery ───────────────────────────────────────────────────────────────
    ("Pizza Dough",            12, _exp(1),  "Ref A"),
    ("Pizza Dough",            14, _exp(3),  "Ref A"),

    # ── Meat ─────────────────────────────────────────────────────────────────
    ("Guanciale",            1200, _exp(10), "Ref B"),
    ("Guanciale",             900, _exp(18), "Ref B"),
    ("Pancetta",             1000, _exp(8),  "Ref B"),
    ("Pancetta",              800, _exp(14), "Ref B"),
    ("Parma Ham",             600, _exp(6),  "Ref B"),
    ("Parma Ham",             700, _exp(12), "Ref B"),
    ("Prosciutto",            600, _exp(5),  "Ref B"),
    ("Prosciutto",            800, _exp(11), "Ref B"),
    ("Cooked Ham",           1200, _exp(4),  "Ref B"),
    ("Cooked Ham",           1500, _exp(9),  "Ref B"),
    ("Salami",                900, _exp(20), "Ref B"),
    ("Salami",                800, _exp(28), "Ref B"),
    ("Spicy Calabrese Salami", 900, _exp(15), "Ref B"),
    ("Spicy Calabrese Salami", 900, _exp(26), "Ref B"),
    ("Italian Sausage",      2000, _exp(3),  "Freezer A"),
    ("Italian Sausage",      2200, _exp(5),  "Freezer A"),
    ("Spicy Italian Sausage", 1500, _exp(4), "Freezer A"),
    ("Ground Beef",          2500, _exp(2),  "Freezer A"),
    ("Ground Beef",          2500, _exp(3),  "Freezer A"),
    ("Wild Boar Meat",        800, _exp(2),  "Freezer B"),   # total 800g → 6 servings  ← LOW

    # ── Seafood ──────────────────────────────────────────────────────────────
    ("Shrimp",               1200, _exp(1),  "Freezer B"),
    ("Shrimp",               1000, _exp(2),  "Freezer B"),
    ("Squid Rings",          1000, _exp(1),  "Freezer B"),
    ("Squid Rings",           900, _exp(2),  "Freezer B"),
    ("Mussels",              1500, _exp(1),  "Freezer B"),
    ("Mussels",              1500, _exp(2),  "Freezer B"),
    ("Clams",                1200, _exp(1),  "Freezer B"),   # total 1200g → 4 servings ← LOW
    ("Anchovy Fillets",        60, _exp(120), "Pantry"),
    ("Anchovy Fillets",        80, _exp(170), "Pantry"),
    ("Canned Tuna",             8, _exp(400), "Pantry"),
    ("Canned Tuna",            10, _exp(500), "Pantry"),

    # ── Dairy ────────────────────────────────────────────────────────────────
    # Buffalo Mozzarella: intentionally absent → OUT OF STOCK
    ("Fresh Mozzarella",     2000, _exp(3),  "Ref A"),
    ("Fresh Mozzarella",     2000, _exp(6),  "Ref A"),
    ("Shredded Mozzarella",  4000, _exp(8),  "Ref A"),
    ("Shredded Mozzarella",  4000, _exp(12), "Ref A"),
    ("Shredded Mozzarella",  3000, _exp(14), "Ref A"),
    ("Ricotta Cheese",       1500, _exp(4),  "Ref A"),
    ("Ricotta Cheese",       1500, _exp(7),  "Ref A"),
    ("Ricotta Salata",        300, _exp(25), "Ref A"),        # → Norma = 12 ← LOW
    ("Parmesan Cheese",      2000, _exp(60), "Ref A"),
    ("Parmesan Cheese",      2000, _exp(90), "Ref A"),
    ("Pecorino Romano",      1500, _exp(55), "Ref A"),
    ("Pecorino Romano",      1500, _exp(85), "Ref A"),
    ("Gorgonzola Cheese",     800, _exp(12), "Ref A"),
    ("Gorgonzola Cheese",     800, _exp(20), "Ref A"),
    ("Fontina Cheese",        700, _exp(15), "Ref A"),
    ("Fontina Cheese",        700, _exp(28), "Ref A"),
    ("Heavy Cream",             5, _exp(7),  "Ref A"),
    ("Heavy Cream",             5, _exp(13), "Ref A"),
    ("Butter",               2000, _exp(30), "Ref A"),
    ("Butter",               2000, _exp(55), "Ref A"),
    ("Egg",                    60, _exp(12), "Ref A"),
    ("Egg",                    60, _exp(20), "Ref A"),

    # ── Vegetables ───────────────────────────────────────────────────────────
    ("Garlic",                120, _exp(14), "Shelf 1"),
    ("Garlic",                150, _exp(26), "Shelf 1"),
    ("Yellow Onion",           30, _exp(12), "Shelf 1"),
    ("Yellow Onion",           35, _exp(25), "Shelf 1"),
    ("Red Onion",              20, _exp(12), "Shelf 1"),
    ("Red Onion",              25, _exp(25), "Shelf 1"),
    ("Carrot",                 24, _exp(9),  "Ref C"),
    ("Carrot",                 28, _exp(18), "Ref C"),
    ("Celery",                 20, _exp(6),  "Ref C"),
    ("Celery",                 22, _exp(12), "Ref C"),
    ("Zucchini",               14, _exp(4),  "Ref C"),
    ("Zucchini",               16, _exp(9),  "Ref C"),
    ("Eggplant",               12, _exp(4),  "Ref C"),
    ("Eggplant",               14, _exp(9),  "Ref C"),
    ("Bell Pepper",            16, _exp(5),  "Ref C"),
    ("Bell Pepper",            18, _exp(11), "Ref C"),
    ("Fresh Tomatoes",         20, _exp(3),  "Ref C"),
    ("Fresh Tomatoes",         24, _exp(6),  "Ref C"),
    ("Cherry Tomatoes",       800, _exp(3),  "Ref C"),
    ("Cherry Tomatoes",       900, _exp(6),  "Ref C"),
    ("Mushrooms",            2000, _exp(3),  "Ref C"),
    ("Mushrooms",            2000, _exp(6),  "Ref C"),
    ("Spinach",              1000, _exp(2),  "Ref C"),
    ("Spinach",               900, _exp(4),  "Ref C"),
    ("Broccoli Rabe",         900, _exp(2),  "Ref C"),
    ("Broccoli Rabe",         800, _exp(4),  "Ref C"),
    ("Arugula",               500, _exp(2),  "Ref C"),
    ("Arugula",               400, _exp(4),  "Ref C"),

    # ── Seasonings ───────────────────────────────────────────────────────────
    ("Fresh Basil",           250, _exp(2),  "Ref C"),
    ("Fresh Basil",           250, _exp(4),  "Ref C"),
    ("Fresh Parsley",         250, _exp(3),  "Ref C"),
    ("Fresh Parsley",         200, _exp(5),  "Ref C"),
    ("Fresh Rosemary",        150, _exp(5),  "Ref C"),
    ("Fresh Sage",             60, _exp(4),  "Ref C"),
    ("Fresh Sage",             60, _exp(7),  "Ref C"),
    ("Oregano",               300, _exp(200), "Pantry"),
    ("Oregano",               300, _exp(320), "Pantry"),
    ("Chili Flakes",          250, _exp(220), "Pantry"),
    ("Chili Flakes",          250, _exp(340), "Pantry"),
    ("Italian Seasoning",     250, _exp(240), "Pantry"),
    ("Fennel Seeds",          200, _exp(260), "Pantry"),
    ("Black Pepper",          400, _exp(200), "Pantry"),
    ("Black Pepper",          400, _exp(330), "Pantry"),
    ("Salt",                 2000, _exp(500), "Pantry"),
    ("Salt",                 2000, _exp(700), "Pantry"),

    # ── Condiments ───────────────────────────────────────────────────────────
    ("Olive Oil",               6, _exp(300), "Pantry"),
    ("Olive Oil",               6, _exp(450), "Pantry"),
    ("Olive Oil",               6, _exp(520), "Pantry"),
    ("Truffle Oil",             1, _exp(300), "Pantry"),      # 1 bottle → Tartufata = 10 ← LOW

    # ── Pantry ───────────────────────────────────────────────────────────────
    ("Crushed Tomatoes",       36, _exp(300), "Pantry"),
    ("Crushed Tomatoes",       36, _exp(430), "Pantry"),
    ("Crushed Tomatoes",       24, _exp(520), "Pantry"),
    ("Tomato Sauce",           18, _exp(200), "Pantry"),
    ("Tomato Sauce",           18, _exp(300), "Pantry"),
    ("Tomato Sauce",           12, _exp(350), "Pantry"),
    ("Marinara Sauce",          8, _exp(240), "Pantry"),
    ("Marinara Sauce",          8, _exp(330), "Pantry"),
    ("Tomato Paste",           12, _exp(250), "Pantry"),
    ("Tomato Paste",           12, _exp(340), "Pantry"),
    ("Bechamel Sauce",          8, _exp(12),  "Ref A"),
    ("Bechamel Sauce",          8, _exp(25),  "Ref A"),
    ("Basil Pesto",            10, _exp(90),  "Pantry"),
    ("Basil Pesto",            10, _exp(160), "Pantry"),
    ("Cannellini Beans",       18, _exp(300), "Pantry"),
    ("Cannellini Beans",       18, _exp(480), "Pantry"),
    ("Artichoke Hearts",     1200, _exp(90),  "Pantry"),
    ("Artichoke Hearts",     1200, _exp(160), "Pantry"),
    ("Black Olives",         1500, _exp(100), "Pantry"),
    ("Black Olives",         1500, _exp(170), "Pantry"),
    ("Capers",                600, _exp(200), "Pantry"),
    ("Capers",                600, _exp(330), "Pantry"),
    ("Sweet Corn",           1000, _exp(220), "Pantry"),
    ("Sweet Corn",           1000, _exp(340), "Pantry"),
    ("Pine Nuts",             500, _exp(90),  "Pantry"),
    ("Pine Nuts",             500, _exp(160), "Pantry"),
    ("Breadcrumbs",          1000, _exp(100), "Pantry"),
    ("Breadcrumbs",          1000, _exp(170), "Pantry"),
    ("Chicken Broth",          10, _exp(200), "Pantry"),
    ("Chicken Broth",          10, _exp(330), "Pantry"),
    ("Beef Broth",              8, _exp(210), "Pantry"),
    ("Beef Broth",              8, _exp(340), "Pantry"),
    ("Vegetable Broth",         8, _exp(220), "Pantry"),
    ("Vegetable Broth",         8, _exp(350), "Pantry"),

    # ── Dry Goods ────────────────────────────────────────────────────────────
    ("Spaghetti",            10000, _exp(300), "Pantry"),
    ("Spaghetti",            10000, _exp(480), "Pantry"),
    ("Penne",                 8000, _exp(300), "Pantry"),
    ("Penne",                 8000, _exp(480), "Pantry"),
    ("Fettuccine",            6000, _exp(320), "Pantry"),
    ("Fettuccine",            5000, _exp(500), "Pantry"),
    ("Tagliatelle",           5000, _exp(320), "Pantry"),
    ("Tagliatelle",           5000, _exp(500), "Pantry"),
    ("Linguine",              5000, _exp(310), "Pantry"),
    ("Linguine",              5000, _exp(490), "Pantry"),
    ("Bucatini",              4000, _exp(310), "Pantry"),
    ("Bucatini",              4000, _exp(490), "Pantry"),
    ("Tonnarelli",            3000, _exp(300), "Pantry"),
    ("Tonnarelli",            2000, _exp(470), "Pantry"),
    ("Orecchiette",           3000, _exp(300), "Pantry"),
    ("Orecchiette",           2000, _exp(470), "Pantry"),
    ("Pappardelle",           3000, _exp(300), "Pantry"),
    ("Pappardelle",           2000, _exp(470), "Pantry"),
    ("Trofie",                3000, _exp(300), "Pantry"),
    ("Trofie",                2000, _exp(470), "Pantry"),
    ("Rigatoni",              5000, _exp(310), "Pantry"),
    ("Rigatoni",              4000, _exp(490), "Pantry"),
    ("Ditalini",              3000, _exp(320), "Pantry"),
    ("Elbow Macaroni",        3000, _exp(320), "Pantry"),
    ("Lasagne Sheets",          96, _exp(300), "Pantry"),
    ("Lasagne Sheets",          96, _exp(460), "Pantry"),
    ("Cannelloni Tubes",        72, _exp(300), "Pantry"),
    ("Cannelloni Tubes",        72, _exp(460), "Pantry"),
    ("Manicotti Shells",        48, _exp(300), "Pantry"),
    ("Manicotti Shells",        48, _exp(460), "Pantry"),

    # ── Frozen ───────────────────────────────────────────────────────────────
    ("Tortellini",            3000, _exp(40), "Freezer A"),
    ("Tortellini",            3000, _exp(75), "Freezer A"),
    ("Spinach & Ricotta Ravioli", 3000, _exp(40), "Freezer A"),
    ("Spinach & Ricotta Ravioli", 2500, _exp(75), "Freezer A"),
    ("Potato Gnocchi",        3000, _exp(45), "Freezer A"),
    ("Potato Gnocchi",        2500, _exp(80), "Freezer A"),

    # ── Beverages: kitchen alcohol ───────────────────────────────────────────
    ("Dry White Wine",           6, _exp(400), "Cellar"),
    ("Dry White Wine",           6, _exp(650), "Cellar"),
    ("Red Wine",                 6, _exp(500), "Cellar"),
    ("Red Wine",                 6, _exp(700), "Cellar"),
    ("Vodka",                    2, _exp(1500), "Bar"),

    # ── Beverages: wine list ─────────────────────────────────────────────────
    ("Chianti",                 12, _exp(1200), "Cellar"),
    ("Chianti",                 12, _exp(1700), "Cellar"),
    ("Barolo",                   6, _exp(1500), "Cellar"),
    ("Barolo",                   6, _exp(1800), "Cellar"),
    ("Barbaresco",               6, _exp(1500), "Cellar"),
    ("Brunello di Montalcino",   6, _exp(1600), "Cellar"),
    ("Amarone della Valpolicella", 6, _exp(1600), "Cellar"),
    ("Montepulciano d'Abruzzo", 12, _exp(1100), "Cellar"),
    ("Nero d'Avola",            12, _exp(1100), "Cellar"),
    ("Primitivo",               12, _exp(1150), "Cellar"),
    ("Valpolicella Classico",   10, _exp(900),  "Cellar"),
    ("Lambrusco",               10, _exp(600),  "Cellar"),
    ("Pinot Grigio",            18, _exp(550),  "Cellar"),
    ("Pinot Grigio",            12, _exp(700),  "Cellar"),
    ("Soave",                   12, _exp(560),  "Cellar"),
    ("Verdicchio",              12, _exp(570),  "Cellar"),
    ("Gavi",                    10, _exp(580),  "Cellar"),
    ("Vermentino",              10, _exp(590),  "Cellar"),
    ("Prosecco",                18, _exp(500),  "Cellar"),
    ("Prosecco",                12, _exp(650),  "Cellar"),
    ("Franciacorta",             8, _exp(660),  "Cellar"),
    ("Asti Spumante",            8, _exp(620),  "Cellar"),
    ("Moscato d'Asti",           8, _exp(610),  "Cellar"),
    ("Vin Santo",                6, _exp(1700), "Cellar"),
]


# ── RECIPES ───────────────────────────────────────────────────────────────────
# (name, category, serving_size, instructions, [(ingredient, qty_per_serving, unit), ...])
#
# Recipe ingredient units are always the product's usageUnit (or a spoon unit the
# conversion table can reach):
#   measurable products → ml / g (the recipe system converts from pcs via unitSize)
#   non-measurable      → pcs only
#
# Serving conventions:
#   Pizzas  : servingSize 1 → 1 serving = 1 whole pizza, quantities are per pizza.
#   Pasta   : servingSize 4 (6 for the baked trays) → quantities are per plate.
#
# Spoon units are used where a cook would reach for a spoon, which exercises the
# ml<->g conversion end to end:
#   Olive Oil / Truffle Oil (ml stock)  → tbsp is pure volume, no density needed
#   Butter      (g stock, density 0.91) → 1 tbsp = 13.5 g
#   Black Pepper(g stock, density 0.5)  → 1 tsp  = 2.5 g

SEED_RECIPES = [

    # ══ PIZZAS (25) ══════════════════════════════════════════════════════════

    ("Pizza Margherita", "Main Course", 1,
     "1. Preheat the oven to 250°C (480°F).\n"
     "2. Roll out the pizza dough.\n"
     "3. Spread tomato sauce evenly over the dough.\n"
     "4. Add mozzarella slices.\n"
     "5. Bake for 10-12 minutes until the crust is golden.\n"
     "6. Top with fresh basil, drizzle with olive oil and serve.",
     [("Pizza Dough", 1, "pcs"), ("Tomato Sauce", 120, "ml"), ("Fresh Mozzarella", 200, "g"),
      ("Fresh Basil", 5, "g"), ("Olive Oil", 2, "tbsp"), ("Salt", 1, "g")]),

    ("Pizza Marinara", "Main Course", 1,
     "1. Preheat the oven to 250°C (480°F).\n"
     "2. Roll out the dough and spread tomato sauce over the base.\n"
     "3. Add the thinly sliced garlic and oregano.\n"
     "4. Drizzle with olive oil.\n"
     "5. Bake for 10-12 minutes.\n"
     "6. Garnish with fresh basil and serve.",
     [("Pizza Dough", 1, "pcs"), ("Tomato Sauce", 120, "ml"), ("Garlic", 3, "pcs"),
      ("Olive Oil", 2, "tbsp"), ("Oregano", 1, "g"), ("Fresh Basil", 3, "g")]),

    ("Pizza Napoletana", "Main Course", 1,
     "1. Roll out the pizza dough and spread tomato sauce.\n"
     "2. Add the mozzarella.\n"
     "3. Arrange the anchovies and capers evenly.\n"
     "4. Sprinkle oregano and drizzle with olive oil.\n"
     "5. Bake until the cheese bubbles and the crust is golden.",
     [("Pizza Dough", 1, "pcs"), ("Tomato Sauce", 120, "ml"), ("Fresh Mozzarella", 200, "g"),
      ("Anchovy Fillets", 6, "pcs"), ("Capers", 10, "g"), ("Oregano", 1, "g"),
      ("Olive Oil", 1, "tbsp")]),

    ("Pizza Quattro Formaggi", "Main Course", 1,
     "1. Roll out the dough.\n"
     "2. Sprinkle the mozzarella over the base.\n"
     "3. Add pieces of gorgonzola.\n"
     "4. Scatter the fontina and parmesan.\n"
     "5. Drizzle lightly with olive oil.\n"
     "6. Bake until all the cheeses are melted and golden. Serve immediately.",
     [("Pizza Dough", 1, "pcs"), ("Shredded Mozzarella", 100, "g"), ("Gorgonzola Cheese", 50, "g"),
      ("Parmesan Cheese", 50, "g"), ("Fontina Cheese", 50, "g"), ("Olive Oil", 1, "tbsp")]),

    ("Pizza Quattro Stagioni", "Main Course", 1,
     "1. Spread tomato sauce over the dough.\n"
     "2. Add the mozzarella.\n"
     "3. Divide the pizza into four sections.\n"
     "4. Place mushrooms, ham, artichokes and olives in separate sections.\n"
     "5. Bake for 10-12 minutes. Slice and serve.",
     [("Pizza Dough", 1, "pcs"), ("Tomato Sauce", 120, "ml"), ("Shredded Mozzarella", 200, "g"),
      ("Mushrooms", 60, "g"), ("Cooked Ham", 60, "g"), ("Artichoke Hearts", 60, "g"),
      ("Black Olives", 30, "g")]),

    ("Pizza Capricciosa", "Main Course", 1,
     "1. Roll out the dough and spread tomato sauce evenly.\n"
     "2. Cover with mozzarella.\n"
     "3. Add the ham, mushrooms, artichokes and olives.\n"
     "4. Bake until golden.\n"
     "5. Let cool slightly before slicing.",
     [("Pizza Dough", 1, "pcs"), ("Tomato Sauce", 120, "ml"), ("Shredded Mozzarella", 200, "g"),
      ("Cooked Ham", 70, "g"), ("Mushrooms", 70, "g"), ("Artichoke Hearts", 60, "g"),
      ("Black Olives", 30, "g")]),

    ("Pizza Diavola", "Main Course", 1,
     "1. Spread tomato sauce over the dough.\n"
     "2. Add the mozzarella.\n"
     "3. Arrange the spicy salami slices.\n"
     "4. Sprinkle the chilli flakes and drizzle with olive oil.\n"
     "5. Bake until crispy and bubbling. Serve hot.",
     [("Pizza Dough", 1, "pcs"), ("Tomato Sauce", 120, "ml"), ("Shredded Mozzarella", 200, "g"),
      ("Spicy Calabrese Salami", 80, "g"), ("Chili Flakes", 2, "g"), ("Olive Oil", 1, "tbsp")]),

    ("Pizza Prosciutto e Funghi", "Main Course", 1,
     "1. Roll out the dough and spread tomato sauce.\n"
     "2. Add the mozzarella.\n"
     "3. Top with the mushrooms and prosciutto.\n"
     "4. Bake for 10-12 minutes. Slice and serve.",
     [("Pizza Dough", 1, "pcs"), ("Tomato Sauce", 120, "ml"), ("Shredded Mozzarella", 200, "g"),
      ("Prosciutto", 70, "g"), ("Mushrooms", 80, "g")]),

    ("Pizza Romana", "Main Course", 1,
     "1. Spread tomato sauce on the dough.\n"
     "2. Add the mozzarella.\n"
     "3. Arrange the anchovies and capers.\n"
     "4. Sprinkle oregano and drizzle with olive oil.\n"
     "5. Bake until golden. Serve immediately.",
     [("Pizza Dough", 1, "pcs"), ("Tomato Sauce", 120, "ml"), ("Shredded Mozzarella", 180, "g"),
      ("Anchovy Fillets", 6, "pcs"), ("Capers", 15, "g"), ("Oregano", 1, "g"),
      ("Olive Oil", 1, "tbsp")]),

    ("Pizza Siciliana", "Main Course", 1,
     "1. Press the thick dough into a baking tray.\n"
     "2. Spread tomato sauce evenly.\n"
     "3. Add the mozzarella, onions and anchovies.\n"
     "4. Sprinkle the breadcrumbs and oregano, then drizzle with olive oil.\n"
     "5. Bake for 15-20 minutes until the crust is crisp. Cut into squares and serve.",
     [("Pizza Dough", 1, "pcs"), ("Tomato Sauce", 150, "ml"), ("Shredded Mozzarella", 200, "g"),
      ("Yellow Onion", 1, "pcs"), ("Anchovy Fillets", 5, "pcs"), ("Breadcrumbs", 20, "g"),
      ("Oregano", 1, "g"), ("Olive Oil", 2, "tbsp")]),

    ("Pizza Ortolana", "Main Course", 1,
     "1. Preheat the oven to 250°C (480°F).\n"
     "2. Roll out the pizza dough and place it on a pizza tray.\n"
     "3. Spread the tomato sauce evenly and sprinkle over the mozzarella.\n"
     "4. Arrange the zucchini, eggplant, bell pepper and red onion on top.\n"
     "5. Sprinkle with Italian seasoning and drizzle with olive oil.\n"
     "6. Bake for 10-12 minutes until the crust is golden. Slice and serve.",
     [("Pizza Dough", 1, "pcs"), ("Tomato Sauce", 120, "ml"), ("Shredded Mozzarella", 200, "g"),
      ("Zucchini", 1, "pcs"), ("Eggplant", 1, "pcs"), ("Bell Pepper", 1, "pcs"),
      ("Red Onion", 1, "pcs"), ("Italian Seasoning", 2, "g"), ("Olive Oil", 2, "tbsp")]),

    ("Pizza Tonno e Cipolla", "Main Course", 1,
     "1. Roll out the dough and spread tomato sauce evenly.\n"
     "2. Add the mozzarella.\n"
     "3. Scatter the drained tuna over the cheese.\n"
     "4. Top with the sliced red onion.\n"
     "5. Sprinkle oregano, drizzle with olive oil and bake for 10-12 minutes. Serve hot.",
     [("Pizza Dough", 1, "pcs"), ("Tomato Sauce", 120, "ml"), ("Shredded Mozzarella", 200, "g"),
      ("Canned Tuna", 160, "g"), ("Red Onion", 1, "pcs"), ("Oregano", 1, "g"),
      ("Olive Oil", 2, "tbsp")]),

    ("Pizza Boscaiola", "Main Course", 1,
     "1. Roll out the dough and spread tomato sauce over the base.\n"
     "2. Sprinkle the mozzarella evenly.\n"
     "3. Add the mushrooms and the cooked, crumbled sausage.\n"
     "4. Drizzle with olive oil and bake for 10-12 minutes.\n"
     "5. Garnish with chopped parsley before serving.",
     [("Pizza Dough", 1, "pcs"), ("Tomato Sauce", 120, "ml"), ("Shredded Mozzarella", 200, "g"),
      ("Mushrooms", 150, "g"), ("Italian Sausage", 150, "g"), ("Olive Oil", 2, "tbsp"),
      ("Fresh Parsley", 3, "g")]),

    ("Pizza Frutti di Mare", "Main Course", 1,
     "1. Roll out the dough and spread tomato sauce evenly.\n"
     "2. Add the mozzarella.\n"
     "3. Arrange the shrimp, squid rings and mussels over the pizza.\n"
     "4. Drizzle with olive oil.\n"
     "5. Bake for 10-12 minutes until the seafood is cooked. Sprinkle with parsley and serve.",
     [("Pizza Dough", 1, "pcs"), ("Tomato Sauce", 120, "ml"), ("Shredded Mozzarella", 200, "g"),
      ("Shrimp", 100, "g"), ("Squid Rings", 100, "g"), ("Mussels", 100, "g"),
      ("Olive Oil", 2, "tbsp"), ("Fresh Parsley", 3, "g")]),

    ("Pizza Salsiccia", "Main Course", 1,
     "1. Roll out the dough and spread tomato sauce evenly.\n"
     "2. Cover with the mozzarella.\n"
     "3. Add the cooked, crumbled sausage.\n"
     "4. Sprinkle the fennel seeds and drizzle lightly with olive oil.\n"
     "5. Bake for 10-12 minutes. Slice and serve.",
     [("Pizza Dough", 1, "pcs"), ("Tomato Sauce", 120, "ml"), ("Shredded Mozzarella", 200, "g"),
      ("Italian Sausage", 200, "g"), ("Fennel Seeds", 2, "g"), ("Olive Oil", 1, "tbsp")]),

    ("Pizza Bufalina", "Main Course", 1,
     "1. Roll out the pizza dough and spread tomato sauce over the base.\n"
     "2. Add slices of buffalo mozzarella.\n"
     "3. Bake for 10-12 minutes and remove from the oven.\n"
     "4. Top with fresh basil.\n"
     "5. Drizzle with olive oil and season lightly before serving.",
     [("Pizza Dough", 1, "pcs"), ("Tomato Sauce", 120, "ml"), ("Buffalo Mozzarella", 200, "g"),
      ("Fresh Basil", 5, "g"), ("Olive Oil", 2, "tbsp"), ("Salt", 1, "g"),
      ("Black Pepper", 0.5, "g")]),

    ("Pizza Parma", "Main Course", 1,
     "1. Spread tomato sauce over the dough and add the mozzarella.\n"
     "2. Bake until the cheese is melted and the crust is golden.\n"
     "3. Remove from the oven.\n"
     "4. Top with Parma ham, arugula and parmesan shavings.\n"
     "5. Drizzle with olive oil, slice and serve immediately.",
     [("Pizza Dough", 1, "pcs"), ("Tomato Sauce", 120, "ml"), ("Shredded Mozzarella", 200, "g"),
      ("Parma Ham", 100, "g"), ("Arugula", 20, "g"), ("Parmesan Cheese", 20, "g"),
      ("Olive Oil", 1, "tbsp")]),

    ("Pizza Calabrese", "Main Course", 1,
     "1. Roll out the dough and spread tomato sauce evenly.\n"
     "2. Add the mozzarella.\n"
     "3. Arrange the spicy Calabrese salami and olives on top.\n"
     "4. Sprinkle the chilli flakes and drizzle with olive oil.\n"
     "5. Bake for 10-12 minutes. Serve while hot.",
     [("Pizza Dough", 1, "pcs"), ("Tomato Sauce", 120, "ml"), ("Shredded Mozzarella", 200, "g"),
      ("Spicy Calabrese Salami", 90, "g"), ("Black Olives", 40, "g"), ("Chili Flakes", 2, "g"),
      ("Olive Oil", 1, "tbsp")]),

    ("Pizza Vegetariana", "Main Course", 1,
     "1. Roll out the pizza dough and spread tomato sauce evenly.\n"
     "2. Add the mozzarella.\n"
     "3. Arrange the mushrooms, bell pepper, olives, cherry tomatoes and spinach over the cheese.\n"
     "4. Drizzle with olive oil.\n"
     "5. Bake for 10-12 minutes. Slice and serve warm.",
     [("Pizza Dough", 1, "pcs"), ("Tomato Sauce", 120, "ml"), ("Shredded Mozzarella", 200, "g"),
      ("Mushrooms", 80, "g"), ("Bell Pepper", 1, "pcs"), ("Black Olives", 30, "g"),
      ("Cherry Tomatoes", 60, "g"), ("Spinach", 40, "g"), ("Olive Oil", 2, "tbsp")]),

    ("Pizza Bianca", "Main Course", 1,
     "1. Preheat the oven to 250°C (480°F) and roll out the pizza dough.\n"
     "2. Brush the dough with olive oil instead of tomato sauce.\n"
     "3. Sprinkle the minced garlic evenly over the base.\n"
     "4. Add the mozzarella and spoonfuls of ricotta.\n"
     "5. Sprinkle with rosemary, salt, pepper and parmesan.\n"
     "6. Bake for 10-12 minutes until the crust is crisp and the cheese is golden.",
     [("Pizza Dough", 1, "pcs"), ("Shredded Mozzarella", 200, "g"), ("Ricotta Cheese", 100, "g"),
      ("Garlic", 2, "pcs"), ("Olive Oil", 2, "tbsp"), ("Fresh Rosemary", 3, "g"),
      ("Parmesan Cheese", 15, "g"), ("Salt", 1, "g"), ("Black Pepper", 0.5, "g")]),

    ("Pizza Tartufata", "Main Course", 1,
     "1. Preheat the oven to 250°C (480°F) and roll out the pizza dough.\n"
     "2. Spread the mozzarella evenly over the dough.\n"
     "3. Top with the sliced mushrooms.\n"
     "4. Bake for 10-12 minutes until the crust is golden.\n"
     "5. Drizzle with truffle oil and sprinkle parmesan and parsley before serving.",
     [("Pizza Dough", 1, "pcs"), ("Shredded Mozzarella", 200, "g"), ("Mushrooms", 100, "g"),
      ("Truffle Oil", 1, "tbsp"), ("Parmesan Cheese", 50, "g"), ("Fresh Parsley", 3, "g")]),

    ("Pizza Mimosa", "Main Course", 1,
     "1. Roll out the pizza dough and spread tomato sauce evenly.\n"
     "2. Add the mozzarella.\n"
     "3. Sprinkle the diced ham and sweet corn over the top.\n"
     "4. Drizzle lightly with olive oil.\n"
     "5. Bake for 10-12 minutes. Slice and serve hot.",
     [("Pizza Dough", 1, "pcs"), ("Tomato Sauce", 120, "ml"), ("Shredded Mozzarella", 200, "g"),
      ("Cooked Ham", 100, "g"), ("Sweet Corn", 100, "g"), ("Olive Oil", 1, "tbsp")]),

    ("Pizza Napoli", "Main Course", 1,
     "1. Roll out the pizza dough and spread tomato sauce over the base.\n"
     "2. Add the mozzarella.\n"
     "3. Arrange the anchovies and capers evenly.\n"
     "4. Sprinkle oregano and drizzle with olive oil.\n"
     "5. Bake for 10-12 minutes until golden. Serve immediately.",
     [("Pizza Dough", 1, "pcs"), ("Tomato Sauce", 120, "ml"), ("Shredded Mozzarella", 200, "g"),
      ("Anchovy Fillets", 6, "pcs"), ("Capers", 20, "g"), ("Oregano", 1, "g"),
      ("Olive Oil", 1, "tbsp")]),

    ("Pizza Pugliese", "Main Course", 1,
     "1. Roll out the pizza dough and spread tomato sauce evenly.\n"
     "2. Sprinkle the mozzarella over the sauce.\n"
     "3. Add the sliced red onion and the olives.\n"
     "4. Sprinkle oregano and drizzle with olive oil.\n"
     "5. Bake for 10-12 minutes. Slice and serve.",
     [("Pizza Dough", 1, "pcs"), ("Tomato Sauce", 120, "ml"), ("Shredded Mozzarella", 200, "g"),
      ("Red Onion", 1, "pcs"), ("Black Olives", 40, "g"), ("Oregano", 1, "g"),
      ("Olive Oil", 1, "tbsp")]),

    ("Pizza Calzone", "Main Course", 1,
     "1. Preheat the oven to 220°C (425°F) and roll the dough into a large circle.\n"
     "2. Spread tomato sauce on one half of the dough.\n"
     "3. Add the mozzarella, ricotta and ham.\n"
     "4. Fold the dough over into a half-moon and seal the edges with a fork.\n"
     "5. Brush with beaten egg and bake for 18-20 minutes until golden brown.\n"
     "6. Let cool slightly before serving.",
     [("Pizza Dough", 1, "pcs"), ("Shredded Mozzarella", 150, "g"), ("Ricotta Cheese", 100, "g"),
      ("Cooked Ham", 100, "g"), ("Tomato Sauce", 30, "ml"), ("Egg", 1, "pcs"),
      ("Olive Oil", 1, "tbsp")]),

    # ══ PASTA (25) ═══════════════════════════════════════════════════════════

    ("Spaghetti Carbonara", "Main Course", 4,
     "1. Cook the spaghetti until al dente.\n"
     "2. Fry the guanciale until crispy.\n"
     "3. Whisk together the eggs, Pecorino and black pepper.\n"
     "4. Drain the pasta, reserving a little pasta water, and toss it with the guanciale.\n"
     "5. Remove from the heat and stir in the egg mixture.\n"
     "6. Loosen with pasta water until creamy. Serve with extra Pecorino and pepper.",
     [("Spaghetti", 100, "g"), ("Guanciale", 40, "g"), ("Egg", 1, "pcs"),
      ("Pecorino Romano", 25, "g"), ("Black Pepper", 1, "g")]),

    ("Spaghetti Aglio e Olio", "Main Course", 4,
     "1. Cook the spaghetti until al dente.\n"
     "2. Heat the olive oil in a large pan.\n"
     "3. Gently cook the sliced garlic until lightly golden.\n"
     "4. Add the chilli flakes.\n"
     "5. Toss the spaghetti in the pan until coated with the oil.\n"
     "6. Stir in the parsley and serve immediately.",
     [("Spaghetti", 100, "g"), ("Garlic", 2, "pcs"), ("Olive Oil", 1, "tbsp"),
      ("Chili Flakes", 1, "g"), ("Fresh Parsley", 3, "g"), ("Salt", 2, "g")]),

    ("Spaghetti alle Vongole", "Main Course", 4,
     "1. Cook the spaghetti until al dente.\n"
     "2. Heat the olive oil and saute the garlic.\n"
     "3. Add the clams and pour in the white wine.\n"
     "4. Cover and cook until the clams open; discard any that stay shut.\n"
     "5. Toss the spaghetti into the pan and mix with the clam juices.\n"
     "6. Garnish with parsley and serve.",
     [("Spaghetti", 100, "g"), ("Clams", 250, "g"), ("Garlic", 1, "pcs"),
      ("Olive Oil", 1, "tbsp"), ("Dry White Wine", 30, "ml"), ("Fresh Parsley", 3, "g"),
      ("Salt", 1, "g"), ("Black Pepper", 0.5, "g")]),

    ("Spaghetti al Pomodoro", "Main Course", 4,
     "1. Cook the spaghetti until al dente.\n"
     "2. Heat the olive oil and saute the garlic.\n"
     "3. Add the crushed tomatoes and simmer for 15-20 minutes.\n"
     "4. Season with salt and pepper.\n"
     "5. Toss the spaghetti with the sauce and add the fresh basil.\n"
     "6. Serve with grated parmesan.",
     [("Spaghetti", 100, "g"), ("Crushed Tomatoes", 125, "g"), ("Garlic", 1, "pcs"),
      ("Olive Oil", 1, "tbsp"), ("Fresh Basil", 3, "g"), ("Parmesan Cheese", 10, "g"),
      ("Salt", 1, "g"), ("Black Pepper", 0.5, "g")]),

    ("Penne all'Arrabbiata", "Main Course", 4,
     "1. Cook the penne until al dente.\n"
     "2. Heat the olive oil and saute the garlic.\n"
     "3. Stir in the chilli flakes and cook for 30 seconds.\n"
     "4. Add the crushed tomatoes and simmer for 15 minutes; season with salt.\n"
     "5. Toss the penne in the spicy tomato sauce.\n"
     "6. Garnish with parsley and serve with parmesan.",
     [("Penne", 100, "g"), ("Crushed Tomatoes", 125, "g"), ("Garlic", 1, "pcs"),
      ("Olive Oil", 1, "tbsp"), ("Chili Flakes", 1, "g"), ("Fresh Parsley", 3, "g"),
      ("Parmesan Cheese", 10, "g"), ("Salt", 1, "g")]),

    ("Penne alla Vodka", "Main Course", 4,
     "1. Cook the penne until al dente.\n"
     "2. Heat the olive oil and saute the onion until softened, then add the garlic.\n"
     "3. Pour in the vodka and simmer for 2-3 minutes.\n"
     "4. Add the crushed tomatoes and cook for 10 minutes.\n"
     "5. Stir in the heavy cream and parmesan; season with salt and pepper.\n"
     "6. Toss the penne in the sauce, garnish with basil and serve.",
     [("Penne", 100, "g"), ("Yellow Onion", 1, "pcs"), ("Garlic", 1, "pcs"),
      ("Vodka", 30, "ml"), ("Crushed Tomatoes", 125, "g"), ("Heavy Cream", 30, "ml"),
      ("Parmesan Cheese", 12, "g"), ("Olive Oil", 1, "tbsp"), ("Fresh Basil", 2, "g"),
      ("Salt", 1, "g"), ("Black Pepper", 0.5, "g")]),

    ("Fettuccine Alfredo", "Main Course", 4,
     "1. Cook the fettuccine until al dente.\n"
     "2. Melt the butter in a large pan over low heat.\n"
     "3. Stir in the heavy cream and simmer gently.\n"
     "4. Add the parmesan and stir until smooth; season with salt and pepper.\n"
     "5. Toss the fettuccine in the sauce until coated.\n"
     "6. Garnish with parsley and serve immediately.",
     [("Fettuccine", 100, "g"), ("Butter", 2, "tbsp"), ("Heavy Cream", 50, "ml"),
      ("Parmesan Cheese", 25, "g"), ("Fresh Parsley", 2, "g"), ("Salt", 1, "g"),
      ("Black Pepper", 0.5, "g")]),

    ("Fettuccine ai Funghi", "Main Course", 4,
     "1. Cook the fettuccine until al dente.\n"
     "2. Heat the olive oil and saute the mushrooms until browned.\n"
     "3. Add the garlic and cook for 1 minute.\n"
     "4. Stir in the heavy cream and simmer for 5 minutes.\n"
     "5. Add the parmesan and season with salt and pepper.\n"
     "6. Toss the fettuccine in the sauce, garnish with parsley and serve.",
     [("Fettuccine", 100, "g"), ("Mushrooms", 60, "g"), ("Garlic", 1, "pcs"),
      ("Heavy Cream", 50, "ml"), ("Parmesan Cheese", 12, "g"), ("Olive Oil", 10, "ml"),
      ("Fresh Parsley", 2, "g"), ("Salt", 1, "g"), ("Black Pepper", 0.5, "g")]),

    ("Tagliatelle al Ragu", "Main Course", 4,
     "1. Cook the tagliatelle until al dente.\n"
     "2. Heat the olive oil and saute the onion, carrot, celery and garlic.\n"
     "3. Add the ground beef and cook until browned.\n"
     "4. Stir in the tomato paste and crushed tomatoes.\n"
     "5. Simmer for 30-40 minutes and season with salt and pepper.\n"
     "6. Toss the tagliatelle with the ragu, top with parmesan and serve.",
     [("Tagliatelle", 100, "g"), ("Ground Beef", 125, "g"), ("Yellow Onion", 1, "pcs"),
      ("Carrot", 1, "pcs"), ("Celery", 1, "pcs"), ("Garlic", 1, "pcs"),
      ("Crushed Tomatoes", 125, "g"), ("Tomato Paste", 8, "g"), ("Olive Oil", 10, "ml"),
      ("Parmesan Cheese", 12, "g"), ("Salt", 1, "g"), ("Black Pepper", 0.5, "g")]),

    ("Lasagne alla Bolognese", "Main Course", 6,
     "1. Preheat the oven to 180°C (350°F).\n"
     "2. Cook the ground beef with the onion and garlic.\n"
     "3. Add the crushed tomatoes and simmer for 20 minutes.\n"
     "4. Spread a layer of meat sauce in a baking dish.\n"
     "5. Layer lasagne sheets, bechamel, mozzarella and parmesan; repeat.\n"
     "6. Finish with cheese on top and bake for 40-45 minutes.\n"
     "7. Let rest for 10 minutes before serving.",
     [("Lasagne Sheets", 2, "pcs"), ("Ground Beef", 85, "g"), ("Crushed Tomatoes", 85, "g"),
      ("Yellow Onion", 1, "pcs"), ("Garlic", 1, "pcs"), ("Bechamel Sauce", 85, "ml"),
      ("Shredded Mozzarella", 35, "g"), ("Parmesan Cheese", 17, "g"), ("Olive Oil", 5, "ml"),
      ("Salt", 1, "g"), ("Black Pepper", 0.5, "g")]),

    ("Linguine al Pesto", "Main Course", 4,
     "1. Cook the linguine until al dente.\n"
     "2. Reserve a little pasta water before draining.\n"
     "3. Toss the linguine with the basil pesto.\n"
     "4. Add a splash of pasta water if needed.\n"
     "5. Stir in the parmesan and drizzle with olive oil.\n"
     "6. Garnish with pine nuts and serve.",
     [("Linguine", 100, "g"), ("Basil Pesto", 38, "g"), ("Parmesan Cheese", 12, "g"),
      ("Olive Oil", 8, "ml"), ("Pine Nuts", 5, "g")]),

    ("Linguine ai Frutti di Mare", "Main Course", 4,
     "1. Cook the linguine until al dente.\n"
     "2. Heat the olive oil and saute the garlic.\n"
     "3. Add the shrimp, mussels and squid rings and cook for 3-5 minutes.\n"
     "4. Pour in the white wine and simmer.\n"
     "5. Season with salt and pepper and toss in the linguine.\n"
     "6. Garnish with parsley and serve.",
     [("Linguine", 100, "g"), ("Shrimp", 38, "g"), ("Mussels", 38, "g"),
      ("Squid Rings", 38, "g"), ("Garlic", 1, "pcs"), ("Dry White Wine", 30, "ml"),
      ("Olive Oil", 8, "ml"), ("Fresh Parsley", 3, "g"), ("Salt", 1, "g"),
      ("Black Pepper", 0.5, "g")]),

    ("Bucatini all'Amatriciana", "Main Course", 4,
     "1. Cook the bucatini until al dente.\n"
     "2. Fry the guanciale until crispy.\n"
     "3. Add the onion and cook until soft.\n"
     "4. Stir in the crushed tomatoes and simmer for 15 minutes.\n"
     "5. Toss the bucatini in the sauce.\n"
     "6. Sprinkle with Pecorino Romano and black pepper. Serve immediately.",
     [("Bucatini", 100, "g"), ("Guanciale", 38, "g"), ("Crushed Tomatoes", 125, "g"),
      ("Yellow Onion", 1, "pcs"), ("Pecorino Romano", 12, "g"), ("Black Pepper", 1, "g")]),

    ("Bucatini alla Gricia", "Main Course", 4,
     "1. Cook the bucatini until al dente and reserve some pasta water.\n"
     "2. Fry the guanciale until crispy.\n"
     "3. Toss the pasta with the guanciale.\n"
     "4. Add the Pecorino Romano.\n"
     "5. Stir in a little pasta water to create a creamy sauce.\n"
     "6. Season generously with black pepper and serve immediately.",
     [("Bucatini", 100, "g"), ("Guanciale", 38, "g"), ("Pecorino Romano", 19, "g"),
      ("Black Pepper", 1, "g")]),

    # Cacio e Pepe measures the pepper by the TEASPOON so the spoon->grams
    # conversion is demonstrable end to end: 1 tsp black pepper = 2.5 g
    # (density 0.5). Prepare 4 servings and watch Black Pepper drop ~5 g.
    ("Cacio e Pepe", "Main Course", 4,
     "1. Cook the tonnarelli until al dente and reserve the pasta water.\n"
     "2. Toast the black pepper in a dry pan for 1 minute.\n"
     "3. Add a small amount of pasta water to the pan.\n"
     "4. Toss in the cooked pasta.\n"
     "5. Gradually add the Pecorino Romano while stirring continuously.\n"
     "6. Add more pasta water until a creamy sauce forms. Serve immediately.",
     [("Tonnarelli", 100, "g"), ("Pecorino Romano", 25, "g"), ("Black Pepper", 0.5, "tsp")]),

    ("Tortellini in Brodo", "Soup", 4,
     "1. Bring the broth to a gentle boil in a large pot.\n"
     "2. Add the tortellini to the simmering broth.\n"
     "3. Cook for 3-5 minutes for fresh tortellini.\n"
     "4. Season with salt and black pepper.\n"
     "5. Ladle the tortellini and broth into serving bowls.\n"
     "6. Sprinkle with parmesan, garnish with parsley and serve hot.",
     [("Tortellini", 125, "g"), ("Chicken Broth", 375, "ml"), ("Parmesan Cheese", 12, "g"),
      ("Fresh Parsley", 2, "g"), ("Salt", 1, "g"), ("Black Pepper", 0.5, "g")]),

    # The butter here is measured by the TABLESPOON: 1 tbsp = 13.5 g at the
    # seeded density of 0.91 g/ml, so 0.5 tbsp per serving takes ~27 g over 4.
    ("Ravioli Ricotta e Spinaci", "Main Course", 4,
     "1. Bring a large pot of salted water to a boil.\n"
     "2. Cook the ravioli until they float to the surface.\n"
     "3. Melt the butter in a large skillet over medium heat.\n"
     "4. Add the sage leaves and cook until fragrant and the butter begins to brown.\n"
     "5. Drain the ravioli and toss gently to coat in the butter sauce.\n"
     "6. Sprinkle with parmesan, season with black pepper and serve.",
     [("Spinach & Ricotta Ravioli", 125, "g"), ("Butter", 0.5, "tbsp"), ("Fresh Sage", 2, "pcs"),
      ("Parmesan Cheese", 12, "g"), ("Salt", 1, "g"), ("Black Pepper", 0.5, "g")]),

    ("Gnocchi al Gorgonzola", "Main Course", 4,
     "1. Cook the gnocchi until they float to the surface.\n"
     "2. Heat the heavy cream in a saucepan over medium heat.\n"
     "3. Add the gorgonzola and stir until melted.\n"
     "4. Mix in the parmesan.\n"
     "5. Drain the gnocchi and toss gently in the sauce.\n"
     "6. Sprinkle with black pepper and parsley before serving.",
     [("Potato Gnocchi", 125, "g"), ("Gorgonzola Cheese", 38, "g"), ("Heavy Cream", 50, "ml"),
      ("Parmesan Cheese", 12, "g"), ("Fresh Parsley", 2, "g"), ("Black Pepper", 0.5, "g")]),

    ("Orecchiette con Cime di Rapa", "Main Course", 4,
     "1. Cook the orecchiette in salted boiling water.\n"
     "2. Add the broccoli rabe during the last 3-4 minutes of cooking.\n"
     "3. Heat the olive oil in a large skillet.\n"
     "4. Cook the garlic, anchovies and chilli flakes until fragrant.\n"
     "5. Drain the pasta and broccoli rabe and toss everything together.\n"
     "6. Serve immediately with extra olive oil if desired.",
     [("Orecchiette", 100, "g"), ("Broccoli Rabe", 75, "g"), ("Garlic", 1, "pcs"),
      ("Anchovy Fillets", 1, "pcs"), ("Olive Oil", 1, "tbsp"), ("Chili Flakes", 0.5, "g"),
      ("Salt", 1, "g")]),

    ("Pappardelle al Cinghiale", "Main Course", 4,
     "1. Cook the pappardelle until al dente.\n"
     "2. Heat the olive oil and saute the onion, carrot and garlic.\n"
     "3. Add the wild boar and brown on all sides.\n"
     "4. Pour in the red wine and let it reduce.\n"
     "5. Add the crushed tomatoes and rosemary, then simmer 1.5-2 hours until tender.\n"
     "6. Toss the pappardelle with the ragu, top with parmesan and serve.",
     [("Pappardelle", 100, "g"), ("Wild Boar Meat", 125, "g"), ("Yellow Onion", 1, "pcs"),
      ("Carrot", 1, "pcs"), ("Garlic", 1, "pcs"), ("Crushed Tomatoes", 125, "g"),
      ("Red Wine", 30, "ml"), ("Olive Oil", 8, "ml"), ("Fresh Rosemary", 2, "g"),
      ("Parmesan Cheese", 12, "g"), ("Salt", 1, "g"), ("Black Pepper", 0.5, "g")]),

    ("Trofie al Pesto", "Main Course", 4,
     "1. Cook the trofie until al dente.\n"
     "2. Reserve a little pasta water before draining.\n"
     "3. Toss the pasta with the basil pesto.\n"
     "4. Add a splash of pasta water if needed.\n"
     "5. Stir in the parmesan and drizzle with olive oil.\n"
     "6. Garnish with pine nuts and serve.",
     [("Trofie", 100, "g"), ("Basil Pesto", 38, "g"), ("Parmesan Cheese", 12, "g"),
      ("Olive Oil", 8, "ml"), ("Pine Nuts", 5, "g")]),

    ("Cannelloni Ricotta e Spinaci", "Main Course", 6,
     "1. Preheat the oven to 180°C (350°F).\n"
     "2. Mix the ricotta, spinach, salt and pepper.\n"
     "3. Fill each cannelloni tube with the ricotta mixture.\n"
     "4. Spread a layer of tomato sauce in a baking dish and arrange the cannelloni on top.\n"
     "5. Cover with the remaining tomato sauce and the bechamel.\n"
     "6. Sprinkle with mozzarella and parmesan and bake 35-40 minutes until bubbling.",
     [("Cannelloni Tubes", 2, "pcs"), ("Ricotta Cheese", 50, "g"), ("Spinach", 34, "g"),
      ("Tomato Sauce", 85, "ml"), ("Bechamel Sauce", 42, "ml"), ("Shredded Mozzarella", 25, "g"),
      ("Parmesan Cheese", 8, "g"), ("Salt", 1, "g"), ("Black Pepper", 0.5, "g")]),

    ("Manicotti", "Main Course", 4,
     "1. Preheat the oven to 180°C (350°F).\n"
     "2. Cook the manicotti shells until slightly firm.\n"
     "3. Mix the ricotta, half the mozzarella, parmesan, egg, parsley, salt and pepper.\n"
     "4. Fill each shell with the cheese mixture.\n"
     "5. Spread marinara sauce in a baking dish and arrange the manicotti in it.\n"
     "6. Cover with the remaining sauce and mozzarella and bake 30-35 minutes.",
     [("Manicotti Shells", 2, "pcs"), ("Ricotta Cheese", 75, "g"), ("Shredded Mozzarella", 50, "g"),
      ("Parmesan Cheese", 12, "g"), ("Egg", 0.25, "pcs"), ("Marinara Sauce", 125, "ml"),
      ("Fresh Parsley", 2, "g"), ("Salt", 1, "g"), ("Black Pepper", 0.5, "g")]),

    ("Pasta alla Norma", "Main Course", 4,
     "1. Cook the rigatoni until al dente.\n"
     "2. Heat the olive oil and cook the diced eggplant until golden and tender.\n"
     "3. Add the garlic and cook for 1 minute.\n"
     "4. Stir in the crushed tomatoes and simmer for 15 minutes.\n"
     "5. Season with salt and black pepper and toss the pasta with the sauce.\n"
     "6. Top with ricotta salata and fresh basil. Serve immediately.",
     [("Rigatoni", 100, "g"), ("Eggplant", 1, "pcs"), ("Crushed Tomatoes", 125, "g"),
      ("Garlic", 1, "pcs"), ("Olive Oil", 8, "ml"), ("Ricotta Salata", 25, "g"),
      ("Fresh Basil", 3, "g"), ("Salt", 1, "g"), ("Black Pepper", 0.5, "g")]),

    ("Pasta e Fagioli", "Soup", 6,
     "1. Heat the olive oil in a large pot over medium heat.\n"
     "2. Saute the onion, carrot, celery and garlic until softened.\n"
     "3. Stir in the crushed tomatoes, broth and Italian seasoning.\n"
     "4. Add the cannellini beans and simmer for 15-20 minutes.\n"
     "5. Stir in the ditalini and cook until tender; season with salt and pepper.\n"
     "6. Serve hot with grated parmesan and a drizzle of olive oil.",
     [("Ditalini", 42, "g"), ("Cannellini Beans", 133, "g"), ("Yellow Onion", 1, "pcs"),
      ("Carrot", 1, "pcs"), ("Celery", 1, "pcs"), ("Garlic", 1, "pcs"),
      ("Vegetable Broth", 133, "ml"), ("Crushed Tomatoes", 67, "g"), ("Olive Oil", 5, "ml"),
      ("Italian Seasoning", 0.5, "g"), ("Parmesan Cheese", 8, "g"), ("Salt", 1, "g"),
      ("Black Pepper", 0.5, "g")]),
]


# ── PREPARATIONS (production history, last 30 days) ──────────────────────────
# Pizzas are counted in pizzas (servingSize 1), pasta in plates.

SEED_PREPARATIONS = [
    (30, "Pizza Margherita",             14),
    (30, "Spaghetti Carbonara",          10),
    (29, "Pizza Diavola",                 9),
    (28, "Penne all'Arrabbiata",          8),
    (28, "Pizza Quattro Formaggi",        7),
    (27, "Tagliatelle al Ragu",          12),
    (26, "Pizza Margherita",             16),
    (25, "Lasagne alla Bolognese",       12),
    (24, "Pizza Capricciosa",             8),
    (23, "Spaghetti Carbonara",          11),
    (22, "Pizza Prosciutto e Funghi",     9),
    (22, "Cacio e Pepe",                  8),
    (21, "Pizza Margherita",             18),
    (20, "Trofie al Pesto",               7),
    (19, "Pizza Diavola",                11),
    (18, "Bucatini all'Amatriciana",      9),
    (17, "Pizza Quattro Stagioni",        8),
    (16, "Spaghetti al Pomodoro",        10),
    (15, "Pizza Margherita",             15),
    (14, "Gnocchi al Gorgonzola",         8),
    (13, "Pizza Boscaiola",               7),
    (12, "Fettuccine Alfredo",           10),
    (10, "Pizza Margherita",             17),
    (9,  "Spaghetti Carbonara",          12),
    (8,  "Pizza Parma",                   8),
    (7,  "Pasta alla Norma",              9),
    (6,  "Pizza Napoli",                  7),
    (4,  "Tagliatelle al Ragu",          11),
    (3,  "Pizza Diavola",                10),
    (1,  "Pizza Margherita",             16),
]


# ── USED STOCK ────────────────────────────────────────────────────────────────
# Simulates a kitchen mid-service: some bottles/jars/cartons are partially used.
# (product_name, remainingBase, baseUnit)
#   remainingBase = how much is left in the opened unit, in ml or g
SEED_USED_STOCK = [
    # Oils and sauces
    ("Olive Oil",        700, "ml"),  # 1000ml bottle, 300ml used
    ("Truffle Oil",       60, "ml"),  # 100ml bottle, 40ml used
    ("Tomato Sauce",     250, "ml"),  # 700ml jar, 450ml used
    ("Marinara Sauce",   400, "ml"),  # 700ml jar, 300ml used
    ("Bechamel Sauce",   200, "ml"),  # 500ml pack, 300ml used
    ("Basil Pesto",       90, "g"),   # 190g jar, 100g used
    ("Tomato Paste",      60, "g"),   # 150g tube, 90g used
    # Crushed Tomatoes: the open can was finished - no entry (0 remaining)

    # Dairy and broths
    ("Heavy Cream",      450, "ml"),  # 1L carton, 550ml used
    ("Chicken Broth",    600, "ml"),  # 1L carton, 400ml used
    ("Vegetable Broth",  350, "ml"),  # 1L carton, 650ml used

    # Bar and kitchen alcohol
    ("Vodka",            500, "ml"),  # 700ml bottle, 200ml used
    ("Dry White Wine",   300, "ml"),  # 750ml bottle, 450ml used
    ("Red Wine",         400, "ml"),  # 750ml bottle, 350ml used
    ("Chianti",          450, "ml"),  # open bottle on the by-the-glass list
    ("Pinot Grigio",     300, "ml"),  # open bottle on the by-the-glass list
]


# ── MAIN ──────────────────────────────────────────────────────────────────────

def slug(name):
    return (name.strip().lower()
            .replace(" ", "_").replace("/", "_")
            .replace("'", "").replace("(", "").replace(")", "")
            .replace("&", "and"))


def validate():
    """Every product name referenced elsewhere must exist in SEED_PRODUCTS.

    Runs before any write: a typo here would otherwise create batches or
    used_stock docs pointing at a product id that never gets created.
    """
    print("\n=== INTEGRITY CHECK ===")
    known = {name.lower() for name, *_ in SEED_PRODUCTS}
    missing = []

    for (rname, _c, _s, _i, ingredients) in SEED_RECIPES:
        for (iname, _q, _u) in ingredients:
            if iname.lower() not in known:
                missing.append((f"recipe {rname}", iname))
    for (bname, *_rest) in SEED_BATCHES:
        if bname.lower() not in known:
            missing.append(("batch", bname))
    for (uname, *_rest) in SEED_USED_STOCK:
        if uname.lower() not in known:
            missing.append(("used_stock", uname))

    if missing:
        for where, name in missing:
            print(f"  MISSING PRODUCT  '{name}'  (referenced by {where})")
        raise SystemExit(f"\n{len(missing)} reference(s) have no matching product. Fix SEED_PRODUCTS.")

    stocked = {name.lower() for name, *_ in SEED_BATCHES}
    for name in sorted(known - stocked):
        print(f"  no batch (out of stock): {name}")
    print(f"  OK - {len(SEED_PRODUCTS)} products, all recipe/batch/used_stock references resolve.")


def main():
    db = get_db()
    validate()

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
    admin_name = SEED_USERS[0]["fullName"]
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
            "density": suggested_density(name, du),
            "createdAt": fb_fs.SERVER_TIMESTAMP,
            "updatedAt": fb_fs.SERVER_TIMESTAMP,
        }
        product_id_map[name] = doc_id
        if COMMIT:
            db.collection("products").document(doc_id).set(data, merge=True)
        m = f"measurable({usage_unit}, x{unit_size})" if measurable else "not-measurable"
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

    print("  NOTE: Buffalo Mozzarella has no batch → OUT OF STOCK (Pizza Bufalina = 0)")

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
        print(f"  {'SET' if COMMIT else 'DRY'}  preparations/{doc_id}  {prep_date}  {recipe_name} x{servings}")

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

    print("\n── INTENTIONAL SHORTAGES (so the alerts have something to show) ──")
    print("  Buffalo Mozzarella     :  no batch  → Pizza Bufalina        = 0   ← CANNOT COOK")
    print("  Wild Boar Meat         :    800 g   → Pappardelle Cinghiale = 6   ← LOW")
    print("  Clams                  :   1200 g   → Spaghetti Vongole     = 4   ← LOW")
    print("  Truffle Oil            :  1 bottle  → Pizza Tartufata       = 10  ← LOW")
    print("  Ricotta Salata         :    300 g   → Pasta alla Norma      = 12  ← LOW")
    print("  Pizza Dough            :   26 pcs   → expires in 1-3 days         ← EXPIRING")

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
