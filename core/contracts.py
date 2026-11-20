# core/contracts.py
from dataclasses import dataclass, field
from typing import Optional, Literal
from abc import ABC, abstractmethod

SignalType = Literal["official_rank", "sales_volume", "bsr", "bought_past_month", "proxy_position"]

@dataclass
class PlatformRawRecord:
    platform: str
    platform_product_id: str          # ASIN / EPID / offerId / SKU
    title: str
    category_native: str              # platform's own category label
    rank_position: Optional[int]      # None if platform exposes no rank
    rank_metric: Optional[str]        # "BEST_SELLING", "hot", "category_position"
    signal_type: SignalType
    price: Optional[float]
    currency: Optional[str]
    review_count: Optional[int] = None
    rating: Optional[float] = None
    sales_30d: Optional[int] = None   # 1688/API only
    seller_name: Optional[str] = None
    url: Optional[str] = None
    raw: dict = field(default_factory=dict)   # audit trail

class PlatformAdapter(ABC):
    platform_name: str
    @abstractmethod
    def fetch_best_sellers(self, category_native: str, limit: int = 50) -> list[PlatformRawRecord]:
        ...