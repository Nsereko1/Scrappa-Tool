# core/normalization.py
from core.contracts import PlatformRawRecord
from typing import Literal

Confidence = Literal["high", "medium", "low"]

SIGNAL_CONFIDENCE: dict[str, Confidence] = {
    "official_rank": "high",
    "sales_volume": "high",
    "bsr": "high",                 # relative ranking, not absolute units
    "bought_past_month": "medium",
    "proxy_position": "low",
}

def normalize(records: list[PlatformRawRecord]) -> list[dict]:
    out = []
    for r in records:
        confidence = SIGNAL_CONFIDENCE[r.signal_type]
        # Normalized score: rank contribution + optional sales signal
        rank_component = 1.0 / r.rank_position if r.rank_position else 0.0
        sales_component = (r.sales_30d or 0) / 10000.0
        score = round((0.7 * rank_component + 0.3 * sales_component), 4)

        out.append({
            "platform": r.platform,
            "product_id": r.platform_product_id,
            "title": r.title,
            "category_native": r.category_native,
            "category_unified": None,        # filled by CategoryMapper
            "rank_native": r.rank_position,
            "rank_metric": r.rank_metric,
            "normalized_score": score,
            "confidence": confidence,
            "signal_type": r.signal_type,
            "price": r.price,
            "currency": r.currency,
            "sales_30d": r.sales_30d,
            "review_count": r.review_count,
            "seller_name": r.seller_name,
            "url": r.url,
            "raw": r.raw,
        })
    return out