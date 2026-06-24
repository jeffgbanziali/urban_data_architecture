# Rapport de tests de charge — Urban Data Explorer

**À compléter après exécution réelle** (les commandes sont prêtes à lancer).

---

## Conditions du test

- Machine : [à renseigner — ex: Dell XPS 15, Intel Core i7-12700H, 16 GB RAM, WSL2]
- Docker Desktop [version]
- Tous les services démarrés (`docker compose up -d`)
- Population de la base préalable : pipeline complet exécuté (3 DAGs en success)

---

## Test 1 — pgbench (base PostgreSQL Gold)

Initialisation des tables de test pgbench :
```bash
docker compose exec postgres-gold pgbench -i -U gold_user gold
```

Test de charge : 10 connexions concurrentes, 2 threads, 30 secondes :
```bash
docker compose exec postgres-gold pgbench -c 10 -j 2 -T 30 -U gold_user gold
```

**Résultats bruts :**
```
# Coller ici la sortie complète de pgbench
```

| Métrique | Valeur |
|---|---|
| TPS (transactions/s) | [à renseigner] |
| Latence moyenne (ms) | [à renseigner] |
| Latence p95 (ms) | [à renseigner] |

**Conclusion :** [La base tient-elle la charge à cette échelle ? Où est la limite observée ?]

---

## Test 2 — Charge API (50 requêtes concurrentes)

```bash
pip install httpx
python tests/test_charge_api.py --base-url http://localhost:8000 --duration 30 --concurrency 50
```

**Résultats bruts :**
```
# Coller ici la sortie de test_charge_api.py
```

| Métrique | Valeur |
|---|---|
| Total requêtes | [à renseigner] |
| Taux d'erreur | [à renseigner] % |
| Débit | [à renseigner] req/s |
| Latence p50 | [à renseigner] ms |
| Latence p95 | [à renseigner] ms |
| Latence max | [à renseigner] ms |

**Endpoints testés :** `/arrondissements`, `/prix?annee=2024`, `/geo/arrondissements`

**Conclusion :** [L'API tient-elle 50 req concurrentes ? Où est le goulot d'étranglement (CPU, DB, réseau) ?]

---

## Analyse

[À remplir après les vrais tests — points à documenter :]
- La limite observée (TPS max avant dégradation)
- Le goulot d'étranglement identifié
- Ce qu'il faudrait changer pour passer à l'échelle supérieure
