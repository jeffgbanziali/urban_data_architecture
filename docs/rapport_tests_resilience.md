# Rapport de tests de résilience — Urban Data Explorer

**À compléter après exécution** — lancer `bash tests/test_resilience.sh` et coller la sortie ici.

---

## Mécanismes de résilience implémentés

| Composant | Mécanisme | Code |
|---|---|---|
| MinIO indisponible | Repli sur `pipeline/bronze/reference/arrondissements.geojson` local | `api/app/routers/geo.py` + `pipeline/bronze/geo_utils.py::load_reference_geojson` |
| Sources réseau indisponibles (ingestion) | Chaque source est indépendante, les autres continuent | `pipeline/bronze/download_sources.py::handle_source` |
| Vélib API indisponible | Log + skip silencieux (pas de données inventées) | `streaming/producer_realtime.py::fetch_real_velib_events` |
| WAQI indisponible (sans token) | Repli synthétique documenté + `make_air_quality_event` | `streaming/producer_realtime.py` |
| Kafka indisponible au démarrage | Retry avec backoff (20 tentatives × 5s) | `streaming/consumer_to_gold.py::connect_consumer_with_retry` |
| PostgreSQL indisponible au démarrage | Retry avec backoff (20 tentatives × 5s) | `streaming/consumer_to_gold.py::get_engine_with_retry` |
| MongoDB indisponible | Log + continuation (le bien SQL est déjà persisté) | `api/app/routers/biens.py::_upsert_caracteristiques_mongo` |
| DAG Airflow échoué | 2 retries automatiques avec délai 5 min | `airflow/dags/dag_*.py::default_args` |

---

## Résultats des scénarios de test

```bash
# Sortie de : bash tests/test_resilience.sh
# [à coller ici après exécution]
```

### Scénario 1 — MinIO arrêté

- **Comportement attendu** : `GET /geo/arrondissements` retourne HTTP 200 avec les 20 arrondissements (repli GeoJSON local)
- **Résultat observé** : [PASS / FAIL]
- **Temps de récupération** : immédiat (repli local, pas de timeout réseau)

### Scénario 2 — Producer Kafka arrêté

- **Comportement attendu** : le consumer reste en attente sans planter ; le flux reprend après redémarrage du producer
- **Résultat observé** : [PASS / FAIL]
- **Temps de récupération** : [à renseigner]

### Scénario 3 — MongoDB arrêté

- **Comportement attendu** : `GET /biens` et `GET /geo/arrondissements` fonctionnent normalement (MongoDB n'est pas sur le chemin critique de ces endpoints)
- **Résultat observé** : [PASS / FAIL]
- **Note** : `GET /biens/{id}/caracteristiques` et `POST /biens` avec caractéristiques retourneront 503 en mode dégradé — comportement attendu et documenté

---

## Conclusion

[À compléter après les vrais tests — les mécanismes fonctionnent-ils comme prévu ?
Quels scénarios ont révélé des failles non anticipées ?]
