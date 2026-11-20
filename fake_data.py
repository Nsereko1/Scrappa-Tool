# test_comparison.py
"""
Test scrape_similar_products clustering against fake_products.json.
Run either as: python test_comparison.py
         or:  pytest test_comparison.py -v
"""

import json
import sys
from typing import Dict, List

# Import the clustering bits from your main script
from scrape_similar_products import (
    _tokens, _signature, similarity, cluster_products, to_usd,
)

FAKE_FILE = "fake_products.json"


def load_items() -> List[Dict]:
    try:
        with open(FAKE_FILE, encoding="utf-8") as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"ERROR: {FAKE_FILE} not found. Run `python fake_data.py` first.")
        sys.exit(1)


def canon_of(title: str, catalogue: List[Dict]) -> str:
    """Map a title back to its canonical product name by best match."""
    best, best_score = "??", 0.0
    for entry in catalogue:
        score = similarity(title, entry["canonical"])
        if score > best_score:
            best_score, best = score, entry["canonical"]
    return best if best_score >= 0.25 else "NOISE"


def load_catalogue():
    from fake_data import CATALOGUE
    return CATALOGUE


# ---------------------------------------------------------------------------
# Test 1: tokenizer + similarity sanity
# ---------------------------------------------------------------------------
def test_similarity_positive():
    print("\n[Test 1] Similarity sanity")
    s = similarity(
        "Samsung Galaxy A14 128GB Dual SIM Black",
        "Samsung Galaxy A14 128GB Storage Smartphone",
    )
    print(f"  same-product similarity = {s:.3f}  (expect > 0.45)")
    assert s > 0.45, f"Similar items scored too low: {s}"

    s_diff = similarity(
        "Samsung Galaxy A14 128GB",
        "Dell XPS 13 Laptop i7",
    )
    print(f"  different-product similarity = {s_diff:.3f}  (expect < 0.15)")
    assert s_diff < 0.15, f"Unrelated items scored too high: {s_diff}"

    s_iphone = similarity("iPhone 13 128GB", "iPhone 14 Pro Max 256GB")
    print(f"  iPhone 13 vs 14 similarity = {s_iphone:.3f}  (expect 0.2–0.55)")
    assert 0.15 < s_iphone < 0.6, f"Near-match scored out of range: {s_iphone}"
    print("  ✓ PASS")


# ---------------------------------------------------------------------------
# Test 2: currency conversion
# ---------------------------------------------------------------------------
def test_currency():
    print("\n[Test 2] Currency conversion")
    assert to_usd(150000, "NGN") == 100.0, to_usd(150000, "NGN")
    assert to_usd(380000, "UGX") == 100.0, to_usd(380000, "UGX")
    assert to_usd(100, "USD") == 100.0
    assert to_usd(720, "CNY") == 100.0, to_usd(720, "CNY")
    print("  NGN/UGX/USD/CNY → USD all correct")
    print("  ✓ PASS")


# ---------------------------------------------------------------------------
# Test 3: clustering at standard threshold
# ---------------------------------------------------------------------------
def test_clusters_standard():
    print("\n[Test 3] Clustering @ threshold=0.35")
    items = load_items()
    catalogue = load_catalogue()
    clusters = cluster_products(items, threshold=0.35, min_platforms=2)

    print(f"  {len(items)} items → {len(clusters)} clusters")

    # Map each cluster back to canonical products
    cluster_canon: List[List[str]] = []
    for c in clusters:
        canon = sorted({canon_of(it["title"], catalogue) for it in c})
        plats = sorted({it["platform"] for it in c})
        cluster_canon.append(canon)
        print(f"    - {canon}  [{len(plats)} platforms: {', '.join(plats)}]")

    # Expected: 6 real products should be found
    found_canon = {c for group in cluster_canon for c in group if c != "NOISE"}
    expected = {
        "Samsung Galaxy A14 128GB",
        "iPhone 13 128GB",
        "Nike Air Max 90",
        "Sony WH-1000XM5",
        "Oraimo 20000mAh Power Bank",
        "Xiaomi Redmi Note 12",
    }
    missing = expected - found_canon
    assert not missing, f"Missing expected products: {missing}"

    # No cluster should be pure noise
    for canon in cluster_canon:
        assert canon != ["NOISE"], \
            f"Noise items falsely clustered: {canon}"

    print(f"  ✓ PASS — all 6 expected products found, no noise clusters")


# ---------------------------------------------------------------------------
# Test 4: high threshold splits near-matches
# ---------------------------------------------------------------------------
def test_high_threshold_splits():
    print("\n[Test 4] High threshold @ 0.55 splits iPhone 13 vs iPhone 14")
    items = load_items()
    catalogue = load_catalogue()

    low = cluster_products(items, threshold=0.35, min_platforms=2)
    high = cluster_products(items, threshold=0.55, min_platforms=2)
    print(f"  clusters: threshold=0.35 → {len(low)} | threshold=0.55 → {len(high)}")

    # At high threshold, iPhone 13 and iPhone 14 should not be in same cluster
    for c in high:
        canon = {canon_of(it["title"], catalogue) for it in c}
        if "iPhone 13 128GB" in canon:
            assert "iPhone 14 Pro Max" not in canon, \
                "iPhone 13 and 14 stayed merged at threshold=0.55"
        if "iPhone 14 Pro Max" in canon:
            assert "iPhone 13 128GB" not in canon, \
                "iPhone 14 and 13 stayed merged at threshold=0.55"
    print("  iPhone 13 and iPhone 14 correctly split")
    print("  ✓ PASS")


# ---------------------------------------------------------------------------
# Test 5: no noise-only cluster at any reasonable threshold
# ---------------------------------------------------------------------------
def test_noise_rejected():
    print("\n[Test 5] Noise rejection @ 0.35")
    items = load_items()
    catalogue = load_catalogue()
    clusters = cluster_products(items, threshold=0.35, min_platforms=2)

    for c in clusters:
        canon = {canon_of(it["title"], catalogue) for it in c}
        assert "NOISE" not in canon or len(canon) > 1, \
            f"Pure-noise cluster found: {[x['title'] for x in c]}"
    print(f"  {len(clusters)} clusters, none are pure noise")
    print("  ✓ PASS")


# ---------------------------------------------------------------------------
# Test 6: every cluster spans ≥ 2 platforms
# ---------------------------------------------------------------------------
def test_cross_platform():
    print("\n[Test 6] All clusters span ≥ 2 platforms")
    items = load_items()
    clusters = cluster_products(items, threshold=0.35, min_platforms=2)
    for c in clusters:
        plats = {x["platform"] for x in c}
        assert len(plats) >= 2, f"Single-platform cluster leaked: {plats}"
    print(f"  All {len(clusters)} clusters span ≥ 2 platforms")
    print("  ✓ PASS")


# ---------------------------------------------------------------------------
# Test 7: prices convert correctly across the report
# ---------------------------------------------------------------------------
def test_prices_in_usd():
    print("\n[Test 7] All cluster items convert to USD cleanly")
    items = load_items()
    for it in items:
        usd = to_usd(it["price"], it["currency"])
        assert usd is not None and usd > 0, \
            f"Bad conversion: {it['currency']} {it['price']} → {usd}"
    print(f"  All {len(items)} items convert cleanly")
    print("  ✓ PASS")


# ---------------------------------------------------------------------------
# Main (plain-script mode)
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    tests = [
        test_similarity_positive,
        test_currency,
        test_clusters_standard,
        test_high_threshold_splits,
        test_noise_rejected,
        test_cross_platform,
        test_prices_in_usd,
    ]
    passed, failed = 0, 0
    for t in tests:
        try:
            t()
            passed += 1
        except AssertionError as e:
            failed += 1
            print(f"  ✗ FAIL: {e}")
        except Exception as e:
            failed += 1
            print(f"  ✗ ERROR: {type(e).__name__}: {e}")
    print("\n" + "=" * 60)
    print(f"RESULT: {passed} passed, {failed} failed")
    print("=" * 60)
    sys.exit(0 if failed == 0 else 1)