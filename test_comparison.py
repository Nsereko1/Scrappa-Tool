# test_comparison.py — corrected
import json
import sys
from typing import Dict, List

from scrape_similar_products import (
    _tokens, _signature, similarity, cluster_products, to_usd, RATES,
)

FAKE_FILE = "fake_products.json"


def load_items() -> List[Dict]:
    with open(FAKE_FILE, encoding="utf-8") as f:
        return json.load(f)


def load_catalogue():
    from fake_data import CATALOGUE
    return CATALOGUE


def canon_of(title: str, catalogue: List[Dict]) -> str:
    best, best_score = "??", 0.0
    for entry in catalogue:
        s = similarity(title, entry["canonical"])
        if s > best_score:
            best_score, best = s, entry["canonical"]
    return best if best_score >= 0.25 else "NOISE"


def test_similarity_positive():
    print("\n[Test 1] Similarity sanity")
    s = similarity("Samsung Galaxy A14 128GB Dual SIM Black",
                   "Samsung Galaxy A14 128GB Storage Smartphone")
    print(f"  same-product    = {s:.3f}  (expect > 0.45)")
    assert s > 0.45, s
    s_diff = similarity("Samsung Galaxy A14 128GB", "Dell XPS 13 Laptop i7")
    print(f"  different       = {s_diff:.3f}  (expect < 0.15)")
    assert s_diff < 0.15, s_diff
    s_iphone = similarity("iPhone 13 128GB", "iPhone 14 Pro Max 256GB")
    print(f"  iPhone 13 vs 14 = {s_iphone:.3f}  (expect 0.15-0.60)")
    assert 0.15 < s_iphone < 0.6, s_iphone
    print("  PASS")


def test_currency():
    """Prove to_usd reverses RATES regardless of what live rate was fetched."""
    print("\n[Test 2] Currency conversion (rate-agnostic)")
    for cur, local in [("NGN", 150000), ("UGX", 380000),
                       ("USD", 100), ("CNY", 720), ("KES", 7500)]:
        rate = RATES.get(cur, 1.0)
        want = round(local / rate, 2)
        got = to_usd(local, cur)
        print(f"  {cur} {local:>10,.2f} / {rate:>7.2f} = ${got:>10,.2f}")
        assert got == want, f"{cur}: expected {want}, got {got}"
    # USD must be identity
    assert to_usd(100, "USD") == 100.0
    print("  PASS")


def test_clusters_standard():
    print("\n[Test 3] Clustering @ threshold=0.35")
    items = load_items()
    catalogue = load_catalogue()
    clusters = cluster_products(items, threshold=0.35, min_platforms=2)
    print(f"  {len(items)} items -> {len(clusters)} clusters")

    cluster_canon = []
    for c in clusters:
        canon = sorted({canon_of(it["title"], catalogue) for it in c})
        plats = sorted({it["platform"] for it in c})
        cluster_canon.append(canon)
        print(f"    - {canon}  [{len(plats)} platforms]")

    # All 6 core products must be found
    found = {x for g in cluster_canon for x in g if x != "NOISE"}
    expected = {
        "Samsung Galaxy A14 128GB", "iPhone 13 128GB", "Nike Air Max 90",
        "Sony WH-1000XM5", "Oraimo 20000mAh Power Bank",
        "Xiaomi Redmi Note 12",
    }
    missing = expected - found
    assert not missing, f"Missing expected products: {missing}"

    # A cluster of NOISE is only "bad" if its members have DIFFERENT
    # base titles (i.e. two unrelated products got merged). Identical
    # titles with different suffixes are legitimate duplicates.
    for c in clusters:
        canon = {canon_of(it["title"], catalogue) for it in c}
        if canon == {"NOISE"}:
            bases = {it["title"].rsplit(" ZX", 1)[0] for it in c}
            assert len(bases) == 1, \
                f"Merged unrelated noise: {sorted(bases)}"
    print("  PASS")


def test_high_threshold_splits():
    print("\n[Test 4] Threshold=0.55 splits iPhone 13 vs 14")
    items = load_items()
    catalogue = load_catalogue()
    high = cluster_products(items, threshold=0.55, min_platforms=2)
    for c in high:
        canon = {canon_of(it["title"], catalogue) for it in c}
        if "iPhone 13 128GB" in canon:
            assert "iPhone 14 Pro Max" not in canon, \
                f"iPhone 13 and 14 merged at 0.55: {canon}"
    print("  PASS")


def test_noise_rejected():
    print("\n[Test 5] Noise rejection @ 0.35")
    items = load_items()
    catalogue = load_catalogue()
    clusters = cluster_products(items, threshold=0.35, min_platforms=2)

    for c in clusters:
        canon = {canon_of(it["title"], catalogue) for it in c}
        if canon == {"NOISE"}:
            bases = {it["title"].rsplit(" ZX", 1)[0] for it in c}
            assert len(bases) == 1, \
                f"Mixed noise cluster: {sorted(bases)}"
    print(f"  {len(clusters)} clusters, no cross-base noise clusters")
    print("  PASS")


def test_cross_platform():
    print("\n[Test 6] All clusters span >= 2 platforms")
    for c in cluster_products(load_items(), threshold=0.35, min_platforms=2):
        plats = {x["platform"] for x in c}
        assert len(plats) >= 2, f"Single-platform cluster: {plats}"
    print("  PASS")


def test_prices_in_usd():
    print("\n[Test 7] All items convert to USD cleanly")
    for it in load_items():
        usd = to_usd(it["price"], it["currency"])
        assert usd is not None and usd > 0, \
            f"Bad conversion: {it['currency']} {it['price']} -> {usd}"
    print("  PASS")


if __name__ == "__main__":
    tests = [
        test_similarity_positive, test_currency, test_clusters_standard,
        test_high_threshold_splits, test_noise_rejected,
        test_cross_platform, test_prices_in_usd,
    ]
    passed = failed = 0
    for t in tests:
        try:
            t(); passed += 1
        except AssertionError as e:
            failed += 1
            print(f"  FAIL: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR: {type(e).__name__}: {e}")
    print("\n" + "=" * 60)
    print(f"RESULT: {passed} passed, {failed} failed")
    print("=" * 60)
    sys.exit(0 if failed == 0 else 1)