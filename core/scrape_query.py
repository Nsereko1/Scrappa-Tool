from typing import Optional
# core/scrape_query.py
"""
Shared query/category filtering for adapters.

- CATEGORIES:   common e-commerce categories → per-platform native slugs
- matches_query: does this product title match a user query?
- filter_by_query: apply the match, with a fallback to unfiltered if empty
"""

import re

# ────────────────────────────────────────────────────────────
# Categories common on e-commerce
# ────────────────────────────────────────────────────────────

CATEGORIES = {
    # key: {label, jumia_slug, keywords (list of matches for filter), kibuga_slug}
    "all": {
        "label": "All Categories",
        "jumia_slug": "all",
        "keywords": [],
    },
    "phones": {
        "label": "Phones & Tablets",
        "jumia_slug": "phones",
        "keywords": ["phone", "iphone", "galaxy", "smartphone",
                     "tecno", "infinix", "itel", "xiaomi", "redmi",
                     "tablet", "ipad", "android"],
    },
    "laptops": {
        "label": "Laptops & Computers",
        "jumia_slug": "phones",
        "keywords": ["laptop", "macbook", "notebook", "computer",
                     "dell", "hp", "lenovo", "thinkpad", "chromebook"],
    },
    "tvs": {
        "label": "TVs & Audio",
        "jumia_slug": "tvs",
        "keywords": ["tv", "television", "hisense", "samsung tv",
                     "lg tv", "smart tv", "led tv", "4k tv", "oled"],
    },
    "audio": {
        "label": "Headphones & Audio",
        "jumia_slug": "tvs",
        "keywords": ["headphone", "earphone", "earbud", "headset",
                     "speaker", "airpods", "wh-1000", "soundbar",
                     "bluetooth speaker", "audio"],
    },
    "fashion": {
        "label": "Fashion & Clothing",
        "jumia_slug": "clothes",
        "keywords": ["shirt", "dress", "jeans", "shoes", "bag",
                     "jacket", "trouser", "top", "blouse", "sneakers"],
    },
    "shoes": {
        "label": "Shoes & Footwear",
        "jumia_slug": "clothes",
        "keywords": ["shoe", "sneaker", "boot", "sandal", "slipper",
                     "nike", "adidas", "puma", "reebok"],
    },
    "home": {
        "label": "Home & Kitchen",
        "jumia_slug": "all",
        "keywords": ["blender", "kettle", "cookware", "furniture",
                     "mattress", "curtain", "rug", "kitchen", "home"],
    },
    "appliances": {
        "label": "Appliances",
        "jumia_slug": "all",
        "keywords": ["fridge", "refrigerator", "freezer", "washing machine",
                     "washer", "dryer", "microwave", "oven", "cooker",
                     "air conditioner", "ac", "air fryer", "vacuum",
                     "iron", "appliance", "dishwasher", "toaster",
                     "coffee maker", "water dispenser", "fan", "heater"],
    },
    "beauty": {
        "label": "Beauty & Health",
        "jumia_slug": "all",
        "keywords": ["perfume", "cream", "lotion", "makeup", "lipstick",
                     "skincare", "shampoo", "soap", "beauty", "cosmetic",
                     "makeup", "serum", "moisturizer"],
    },
    "gaming": {
        "label": "Gaming",
        "jumia_slug": "phones",
        "keywords": ["console", "playstation", "xbox", "nintendo", "ps5",
                     "ps4", "controller", "gaming", "gamepad", "joystick"],
    },
    "accessories": {
        "label": "Accessories",
        "jumia_slug": "phones",
        "keywords": ["case", "cover", "cable", "charger", "adapter",
                     "holder", "screen protector", "accessory"],
    },
    "power": {
        "label": "Power & Chargers",
        "jumia_slug": "phones",
        "keywords": ["power bank", "charger", "adapter", "usb", "battery",
                     "power", "charging", "solar", "generator", "inverter"],
    },
}

DEFAULT_CATEGORY = "all"


def category_choices():
    """For the UI dropdown — [(key, label), ...]."""
    return [(k, v["label"]) for k, v in CATEGORIES.items()]


def jumia_slug(category: str) -> str:
    cat = CATEGORIES.get(category.lower(), CATEGORIES["all"])
    return cat.get("jumia_slug", "all")


def kibuga_keyword(category: str):
    cat = CATEGORIES.get(category.lower(), CATEGORIES["all"])
    kws = cat.get("keywords", [])
    return kws[0] if kws else None


# ────────────────────────────────────────────────────────────
# Query matching
# ────────────────────────────────────────────────────────────

_STOP = {
    "the", "a", "an", "and", "or", "for", "with", "in", "on", "of", "to",
}


def _tokens(text: str) -> set:
    if not text:
        return set()
    t = re.sub(r"[^a-z0-9\s]", " ", text.lower())
    return {w for w in t.split() if w not in _STOP and len(w) > 0}


def matches_query(title: str, query: str) -> bool:
    """
    True if every keyword in `query` appears in `title`.
    `query` should be a short phrase like "macbook pro" or "hisense tv".
    Empty query always matches.
    """
    if not query or not query.strip():
        return True
    q_tokens = _tokens(query)
    if not q_tokens:
        return True
    t_tokens = _tokens(title)
    return q_tokens.issubset(t_tokens)


def filter_by_query(items: list, query: str, log_prefix: str = "") -> list:
    """
    Filter a list of product dicts by `query`. If zero items match,
    return the ORIGINAL list (better to over-scrape than return empty).
    Logs the fallback so you can see it in the terminal.
    """
    if not query or not query.strip():
        return items

    matched = [it for it in items if matches_query(it.get("title", ""), query)]

    if matched:
        if log_prefix:
            print(f"[{log_prefix}] query='{query}' matched {len(matched)}/{len(items)}",
                  flush=True)
        return matched

    if log_prefix:
        print(f"[{log_prefix}] query='{query}' matched 0/{len(items)} — "
              f"using unfiltered (platform may not carry this product)",
              flush=True)
    return items


def category_keywords(category: str) -> list:
    """Return the keyword list for a category (empty list for 'all')."""
    cat = CATEGORIES.get(category.lower(), CATEGORIES["all"])
    return list(cat.get("keywords", []))


def effective_query(category: str, user_query: str = None) -> str:
    """
    Decide what query to pass to adapters:
      - If user typed a query, use it.
      - Else if category has keywords, use the first one (single-word trigger).
      - Else no filter.
    """
    if user_query and user_query.strip():
        return user_query.strip()
    kws = category_keywords(category)
    return kws[0] if kws else None


def matches_category(title: str, category: str) -> bool:
    """True if title matches ANY keyword of the category."""
    kws = category_keywords(category)
    if not kws:
        return True
    t = title.lower()
    return any(kw.lower() in t for kw in kws)
