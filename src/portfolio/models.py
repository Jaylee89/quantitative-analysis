from dataclasses import dataclass


@dataclass
class PortfolioData:
    total_grams: float
    total_cost: float
    avg_cost_per_gram: float
    updated_at: str


@dataclass
class BuyRecord:
    id: int
    grams: float
    price_per_gram: float
    total_amount: float
    bought_at: str
