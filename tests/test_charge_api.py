"""
tests/test_charge_api.py
--------------------------
Test de charge de l'API : 50 requêtes concurrentes sur /prix, /arrondissements
et /geo/arrondissements, répétées pendant 30 secondes. Mesure latence p50/p95
et taux d'erreur.

Usage :
    python tests/test_charge_api.py [--base-url http://localhost:8000] [--duration 30] [--concurrency 50]

Nécessite httpx (pip install httpx) — pas dans les requirements car c'est un
outil de test de charge, pas une dépendance de l'application.
"""
import argparse
import asyncio
import statistics
import time

try:
    import httpx
except ImportError:
    raise SystemExit("Installez httpx : pip install httpx")


ENDPOINTS = [
    "/arrondissements",
    "/prix?annee=2024",
    "/geo/arrondissements",
]


async def single_request(client: httpx.AsyncClient, base_url: str, path: str) -> tuple[float, int]:
    t0 = time.perf_counter()
    try:
        r = await client.get(f"{base_url}{path}", timeout=10.0)
        return time.perf_counter() - t0, r.status_code
    except Exception:
        return time.perf_counter() - t0, 0


async def load_test(base_url: str, duration_s: int, concurrency: int) -> dict:
    results: list[tuple[float, int]] = []
    deadline = time.time() + duration_s

    async with httpx.AsyncClient() as client:
        while time.time() < deadline:
            batch = []
            for i in range(concurrency):
                path = ENDPOINTS[i % len(ENDPOINTS)]
                batch.append(single_request(client, base_url, path))
            batch_results = await asyncio.gather(*batch)
            results.extend(batch_results)

    latencies = [r[0] * 1000 for r in results]  # ms
    status_codes = [r[1] for r in results]
    errors = sum(1 for s in status_codes if s == 0 or s >= 400)

    latencies_sorted = sorted(latencies)
    n = len(latencies_sorted)

    return {
        "total_requests": len(results),
        "errors": errors,
        "taux_erreur_pct": round(100 * errors / max(n, 1), 2),
        "req_par_s": round(len(results) / duration_s, 1),
        "latence_ms": {
            "min": round(min(latencies), 1),
            "p50": round(latencies_sorted[n // 2], 1),
            "p95": round(latencies_sorted[int(n * 0.95)], 1),
            "max": round(max(latencies), 1),
            "moyenne": round(statistics.mean(latencies), 1),
        },
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument("--concurrency", type=int, default=50)
    args = parser.parse_args()

    print(f"Test de charge : {args.concurrency} req concurrentes pendant {args.duration}s sur {args.base_url}")
    print("Endpoints : " + ", ".join(ENDPOINTS))
    print()

    result = asyncio.run(load_test(args.base_url, args.duration, args.concurrency))

    print(f"Total requêtes       : {result['total_requests']}")
    print(f"Erreurs              : {result['errors']} ({result['taux_erreur_pct']}%)")
    print(f"Débit                : {result['req_par_s']} req/s")
    print(f"Latence p50          : {result['latence_ms']['p50']} ms")
    print(f"Latence p95          : {result['latence_ms']['p95']} ms")
    print(f"Latence max          : {result['latence_ms']['max']} ms")
    print()
    print("→ Copier ces résultats dans docs/rapport_tests_charge.md")
    return result


if __name__ == "__main__":
    main()
