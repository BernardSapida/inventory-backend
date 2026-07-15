"""
Backfill `density` (g/ml) on existing product documents.

Products created before the spoon-measurement feature have no `density` field, so
the admin form showed density 0 and a misleading warning (recipes still worked via
a name-based fallback, but the stored data was incomplete). This script sets
`density` on every g-based product whose name matches the known ingredient table -
the same table used by the apps and the seeder.

Semantics of the stored value (see resolveDensity in the apps):
  > 0   → explicit density, used directly
  0     → explicit "no spoons" (leave the toggle off); this script never writes 0
  null  → never configured; app falls back to the name table

This script only fills products that currently have NO density (null/missing) and
whose name matches. It never overwrites a value an admin already set, and it never
writes to non-g products.

Usage (from inventory-backend/):
  venv/Scripts/python.exe scripts/backfill_density.py            # dry run
  venv/Scripts/python.exe scripts/backfill_density.py --commit   # apply
"""

import re
import sys

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.dirname(__import__("os").path.abspath(__file__))))

from db.connection import get_db  # noqa: E402

COMMIT = "--commit" in sys.argv

# MIRRORS DENSITY_DEFAULTS in smartstock-admin/src/lib/units.ts,
# inventory-native/lib/types/product.ts, and scripts/seed_data.py.
DENSITY_DEFAULTS = [
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


def suggested_density(name):
    n = (name or "").strip().lower()
    for pattern, value in DENSITY_DEFAULTS:
        if re.search(pattern, n):
            return value
    return None


def main():
    db = get_db()
    print("\n=== BACKFILL PRODUCT DENSITY ===")
    updated = skipped_has = skipped_nonmass = skipped_nomatch = 0

    for doc in db.collection("products").stream():
        data = doc.to_dict()
        name = data.get("name", doc.id)

        # Only g-based products can carry a density.
        if data.get("baseUnit") != "g":
            skipped_nonmass += 1
            continue

        # Never overwrite an explicit value (including an explicit 0 = "off").
        if data.get("density") is not None:
            skipped_has += 1
            continue

        guess = suggested_density(name)
        if guess is None:
            skipped_nomatch += 1
            print(f"  SKIP  products/{doc.id}  ({name!r} - no name match; left null)")
            continue

        print(f"  {'SET' if COMMIT else 'DRY'}  products/{doc.id}  {name!r} density -> {guess}")
        if COMMIT:
            doc.reference.update({"density": guess})
        updated += 1

    print(
        f"\n── {'DONE' if COMMIT else 'DRY RUN'}: {updated} to set, "
        f"{skipped_has} already have a density, {skipped_nomatch} g-products with no "
        f"name match (left null → fall back at runtime), {skipped_nonmass} non-g skipped. ──"
    )
    if not COMMIT:
        print("── Re-run with --commit to apply. ──")


if __name__ == "__main__":
    main()
