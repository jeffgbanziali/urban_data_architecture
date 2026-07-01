# Urban Immo — Urban Data Explorer
### Projet RNCP40875 · Expert en Ingénierie des données · EFREI

---

## 1. Présentation du projet

Urban Immo est une agence immobilière parisienne fictive dont l'ensemble du site web et des outils internes est piloté par une architecture data complète, construite de A à Z.

**Objectif** : démontrer la maîtrise de toute la chaîne de valeur de la donnée — ingestion de sources ouvertes, nettoyage, modélisation multidimensionnelle, API sécurisée, streaming temps réel et dashboard interactif — dans un contexte métier réaliste.

**Périmètre fonctionnel :**
- Vitrine publique de l'agence (catalogue de biens, filtres, favoris)
- Espaces par rôle : client, employé, administrateur
- Explorateur de données interactif : carte choroplèthe des 20 arrondissements parisiens avec 11 indicateurs réels
- Flux temps réel : qualité de l'air et disponibilité Vélib en direct

---

## 2. Architecture globale

```
Sources ouvertes (DVF, INSEE, OpenData Paris, WAQI, IDFM, SSMSI, RPLS)
        │
        ▼
  DAG ingestion_bronze ───────────►  Zone BRONZE  (MinIO, horodaté)
        │                                   │
        │                       DAG transform_silver (Airflow)
        │                                   ▼
        │                       Zone SILVER  (MinIO, Parquet nettoyé)
        │                                   │
        │                       DAG aggregate_gold (Airflow)
        │                                   ▼
        │                  Zone GOLD : PostgreSQL + GeoJSON MinIO
        │                                   │
  DAG realtime_stream ────────────────────── ┤  (toutes les 3 min)
  WAQI + Vélib → pg_notify                   ▼
                                       API FastAPI  (JWT, rôles, OpenAPI)
                                            │
                                            ▼
                         Frontend React 19 (vitrine + explorateur de données)
```

Le pipeline suit une architecture **médaillon Bronze → Silver → Gold** orchestrée par Apache Airflow. Les données temps réel alimentent PostgreSQL directement via un DAG dédié, sans passer par les zones Bronze/Silver.

---

## 3. Stack technique

| Couche | Technologie | Rôle |
|---|---|---|
| **Frontend** | React 19, TypeScript, Vite, Tailwind v4 | Interface utilisateur |
| **Cartographie** | DeckGL + Mapbox GL | Carte choroplèthe interactive |
| **API** | FastAPI (Python 3.11) | REST + WebSocket |
| **ORM / DB** | SQLAlchemy, psycopg2, asyncpg | Accès PostgreSQL |
| **NoSQL** | MongoDB 7.0 + Motor (async) | Caractéristiques variables des biens |
| **Data Lake** | MinIO (API S3) | Stockage Bronze / Silver / Gold |
| **Orchestration** | Apache Airflow 2.9.3 | 4 DAGs, LocalExecutor |
| **Base relationnelle** | PostgreSQL 16 | Données Gold + auth + schéma étoile |
| **Gouvernance** | Marquez / OpenLineage | Traçabilité du pipeline |
| **Conteneurisation** | Docker Compose | Déploiement local reproductible |

---

## 4. Sources de données

Toutes les sources sont **réelles, publiques et vérifiées** :

| Source | Données | Format |
|---|---|---|
| DVF / geo-dvf (data.gouv.fr) | Transactions immobilières 2021–2025, Paris | CSV.gz |
| INSEE Populations légales 2021 | Population et superficie par commune | CSV |
| RPLS 2021 (data.gouv.fr) | Logements locatifs sociaux par commune | CSV |
| INSEE RP 2021 — logements IRIS | Typologies de logements (maison/appart) | ZIP/CSV |
| OpenData Paris — espaces verts | 500+ espaces verts géolocalisés | JSON |
| WAQI (aqicn.org) | Indice qualité de l'air (stations réelles) | API REST |
| IDFM — gares IDF | Emplacement stations métro/RER | CSV |
| SSMSI (Ministère Intérieur) | Délits par commune (base communale) | CSV.gz |
| OpenData Paris — Vélib | Disponibilité stations en temps réel | API REST |

---

## 5. Pipeline de données

### 5.1 Zone Bronze — Ingestion

`pipeline/bronze/download_sources.py` télécharge les 9 sources et les écrit dans MinIO bucket `bronze` avec un préfixe horodaté `source/YYYY/MM/DD/HHMMSS/`.

Chaque source est traitée **indépendamment** : un échec réseau sur une source ne bloque pas les autres. Un rapport JSON de run (volume, durée, taux de succès par source) est écrit dans MinIO et dans PostgreSQL.

**Résilience** : un fallback sur des données synthétiques est disponible si une source est indisponible le jour J.

### 5.2 Zone Silver — Nettoyage et qualité

`pipeline/silver/clean_silver.py` produit des Parquet propres :

- **DVF** : détection automatique du format geo-dvf réel (colonnes `code_postal`, `valeur_fonciere`), filtrage sur les locaux d'habitation (Appartement / Maison), suppression des doublons et valeurs aberrantes
- **Espaces verts** : résolution d'arrondissement par **point-in-polygon réel** (Shapely + géométries officielles), repli sur code postal si coordonnée absente
- **RPLS** : filtrage communes `75101–75120`, calcul `nb_lls = TOT21`
- **INSEE RP logements** : agrégation IRIS → arrondissement, calcul `pct_appartements`
- **Criminalité** : filtrage arrondissements parisiens, calcul taux pour 1 000 habitants

Rapports qualité versionnés : taux de rétention, doublons supprimés, lignes non géocodées.

### 5.3 Zone Gold — Agrégation et modélisation

`pipeline/gold/aggregate_gold.py` produit :

1. **Tables Gold plat** : `prix_m2_arrondissement`, `indicateurs_socio`
2. **Schéma en étoile** : `dim_arrondissement`, `dim_temps`, `fait_prix_immobilier`
3. **Data marts** : 3 vues matérialisées pré-agrégées
4. **GeoJSON enrichi** : géométries officielles des 20 arrondissements + tous les indicateurs, exporté dans MinIO Gold

**Point notable** : l'écriture PostgreSQL utilise psycopg2 brut (et non `pandas.to_sql`), après un bug de compatibilité entre pandas et l'environnement Airflow documenté dans le README.

**IDW (Inverse Distance Weighting)** : seuls 9 des 20 arrondissements ont une station WAQI. Les 11 arrondissements sans station reçoivent une valeur interpolée par la distance aux stations connues (pondération inverse du carré de la distance).

---

## 6. Bases de données

### 6.1 PostgreSQL 16 — Base relationnelle (C1.1)

Schéma défini dans `sql/01_init_gold.sql` :
- Contraintes CHECK (`arrondissement BETWEEN 1 AND 20`, `prix_m2_median > 0`)
- Clés composites et index de performance
- Rôle lecture seule `gold_reader` pour l'API (principe du moindre privilège)
- Notification asynchrone via `pg_notify` (base du streaming WebSocket)

**Schéma en étoile** (C2.3) :
```
dim_arrondissement  ←──  fait_prix_immobilier  ──►  dim_temps
      ↓
 dim_segment
```

**3 Data Marts** : `mart_marche_immobilier`, `mart_qualite_vie`, `mart_mobilite`
Rafraîchis après chaque run Gold via `REFRESH MATERIALIZED VIEW CONCURRENTLY` (sans bloquer les lectures).

### 6.2 MongoDB 7.0 — Base non-relationnelle (C1.2)

Collection `biens_caracteristiques` : chaque bien a ses propres attributs variables.

```json
// Studio :
{ "bien_id": 12, "type_bien": "Studio", "etage": 4, "ascenseur": true }

// Maison :
{ "bien_id": 27, "type_bien": "Maison", "jardin_m2": 80, "garage": true, "nb_niveaux": 2 }
```

- Driver **Motor** (async) côté FastAPI — zéro blocage I/O
- Écriture **non-bloquante** : si MongoDB est indisponible, un warning est loggé mais l'API répond normalement
- Endpoint dédié : `GET /biens/{id}/caracteristiques`

### 6.3 MinIO — Data Lake (C1.3)

3 buckets isolés, API compatible S3 :

| Bucket | Contenu | Format |
|---|---|---|
| `bronze` | Sources brutes horodatées | CSV, JSON, CSV.gz |
| `silver` | Données nettoyées | Parquet |
| `gold` | GeoJSON enrichi, rapports | GeoJSON, Parquet, JSON |

Versioning horodaté : chaque run crée un nouveau préfixe, les données passées sont conservées. Remplaçable par AWS S3 sans modifier une ligne de code.

---

## 7. API FastAPI (C2.1)

### 7.1 Authentification et sécurité

- **JWT HS256** (8h de validité) — stateless, compatible multi-instances
- **bcrypt** pour le hachage des mots de passe
- `get_current_user` recharge l'utilisateur depuis PostgreSQL à **chaque requête** : la désactivation d'un compte par un admin est immédiatement effective, même avec un token encore valide
- **CORS** configuré, quotas 60 req/min par IP

### 7.2 Trois rôles métier

| Rôle | Droits |
|---|---|
| **Client** | Consultation biens publics, favoris, auto-inscription |
| **Employé** | Tout client + création/modification de biens + explorateur de données |
| **Administrateur** | Tout employé + gestion comptes + suppression biens |

### 7.3 Endpoints principaux

| Endpoint | Rôle | Description |
|---|---|---|
| `POST /auth/login` | public | Token JWT |
| `GET /geo/arrondissements` | public | GeoJSON enrichi (carte) |
| `GET /prix` | public | Prix médian/m² par année |
| `GET /comparaison` | public | Comparaison 2 arrondissements |
| `POST /biens` | employé/admin | Créer un bien (→ PostgreSQL + MongoDB) |
| `GET /biens/{id}/caracteristiques` | public | Attributs libres (MongoDB) |
| `WS /ws/realtime` | public | Push qualité air + Vélib |
| `GET /marts/marche` | public | Data mart marché immobilier |
| `GET /admin/rapports-qualite` | admin | Rapports pipeline (JSONB) |

Documentation complète : http://localhost:8000/docs

---

## 8. Streaming temps réel (C2.2)

### Architecture distribuée

DAG `realtime_stream` (schedule `*/3 * * * *`) avec deux tâches **parallèles** :

```
┌─────────────────────────┐   ┌─────────────────────────┐
│  fetch_air_quality      │   │  fetch_velib             │
│  WAQI → PostgreSQL      │   │  OpenData Paris → PG     │
│  + pg_notify            │   │  + pg_notify             │
└─────────────────────────┘   └─────────────────────────┘
           │                             │
           └──────────┬──────────────────┘
                      ▼
          WebSocket /ws/realtime  (LISTEN/NOTIFY)
```

**Pourquoi c'est distribué** : Airflow LocalExecutor lance chaque tâche dans un **sous-processus Python distinct**. Les deux collectes s'exécutent de façon concurrente, sans état partagé — même principe qu'un consumer group Kafka partitionné par topic, sans le broker intermédiaire.

### Mécanisme de push WebSocket

1. Le DAG insère les données dans PostgreSQL
2. `pg_notify('canal', payload_json)` est appelé immédiatement après
3. Chaque client WebSocket connecté a une connexion asyncpg en `LISTEN`
4. Le push arrive **dans la milliseconde** — aucun polling côté serveur ni côté client

---

## 9. Frontend (React 19)

### Pages et espaces par rôle

| Page | Accès | Fonctionnalité |
|---|---|---|
| Vitrine | public | Catalogue biens, filtres, détail |
| `/explorateur` | employé+ | Carte choroplèthe + 11 indicateurs |
| `/favoris` | client+ | Biens sauvegardés |
| `/admin` | admin | Gestion comptes et rapports |

### Explorateur de données

- **Carte choroplèthe** : DeckGL + Mapbox GL sur les géométries officielles des 20 arrondissements
- **Palettes de couleurs par catégorie** : logement (bleu), environnement (vert), sécurité (rouge/orange), transport (violet), social (amber)
- **11 indicateurs** sélectionnables via onglets catégorisés
- **Tooltip** au survol : valeur de l'indicateur + population de l'arrondissement
- **Légende dynamique** avec badge "Faible variation" quand l'écart inter-arrondissements est < 5 %
- **Flux temps réel** : widget Vélib et qualité de l'air mis à jour sans rechargement

### Token Mapbox

Stocké dans `frontend/.env` (exclu du dépôt git), injecté à la build via `VITE_MAPBOX_TOKEN`. Aucun token en dur dans le code source.

---

## 10. Indicateurs de l'explorateur

### 4 indicateurs obligatoires

| Indicateur | Source | Colonne PostgreSQL |
|---|---|---|
| Prix/m² médian | DVF 2021–2025 (data.gouv.fr) | `prix_m2_arrondissement.prix_m2_median` |
| Évolution annuelle du prix | Calculée depuis DVF | `prix_m2_arrondissement.variation_pct` |
| Logements sociaux (%) | RPLS 2021 (data.gouv.fr) | `indicateurs_socio.pct_logements_sociaux` |
| Typologie logements | INSEE RP 2021 IRIS | `indicateurs_socio.pct_appartements` |

### 7 indicateurs personnalisés

| Indicateur | Source |
|---|---|
| Qualité de l'air (IQA) | WAQI (stations réelles) + IDW interpolation |
| Population | INSEE Populations légales 2021 |
| Densité (hab/km²) | INSEE Populations légales 2021 |
| Espaces verts | OpenData Paris + point-in-polygon |
| Criminalité (faits/1 000 hab) | SSMSI — Base communale délits |
| Stations Métro/RER | IDFM emplacement des gares IDF |
| Stations Vélib | OpenData Paris — Vélib disponibilité |

---

## 11. Tests

### Tests unitaires et d'intégration

```bash
pytest tests/ -v
# Pas de dépendance à Docker — base SQLite en mémoire
```

| Fichier | Ce qu'il valide |
|---|---|
| `test_transform.py` | Nettoyage Silver (DVF, espaces verts, format réel geo-dvf) |
| `test_aggregate.py` | Fusion GeoJSON officiel + indicateurs Gold |
| `test_geo_utils.py` | Point-in-polygon Shapely (monuments parisiens connus) |
| `test_api.py` | Auth JWT, contrôle d'accès par rôle, CRUD biens, favoris |
| `test_charge_api.py` | 50 requêtes concurrentes — latence p50/p95, taux d'erreur |
| `test_realtime_integration.py` | Push WebSocket via LISTEN/NOTIFY PostgreSQL réel |

`test_realtime_integration.py` est automatiquement ignoré (skip) si aucun PostgreSQL n'est accessible — la commande `pytest tests/` reste toujours utilisable sans Docker.

### Tests de résilience

Script `tests/test_resilience.sh` — coupe des services et vérifie les replis :

1. MinIO arrêté → `GET /geo/arrondissements` sert le GeoJSON de référence local
2. Réseau sortant coupé → pipeline continue (lignes non géocodées tracées)
3. MongoDB indisponible → `POST /biens` répond 201 normalement (warning loggé)

---

## 12. Orchestration et gouvernance

### Airflow — 4 DAGs

| DAG | Schedule | Rôle |
|---|---|---|
| `ingestion_bronze` | 2h00 quotidien | Télécharge les 9 sources → MinIO Bronze |
| `transform_silver` | Déclenché par bronze | Nettoie → Parquet Silver |
| `aggregate_gold` | Déclenché par silver | Agrège → PostgreSQL + GeoJSON Gold |
| `realtime_stream` | `*/3 * * * *` | Vélib + WAQI → PostgreSQL + pg_notify |

Retries automatiques : 2 tentatives, délai 5 minutes.

### Marquez / OpenLineage — Gouvernance

Chaque run Airflow émet des événements OpenLineage vers Marquez automatiquement (provider `apache-airflow-providers-openlineage`).

L'UI Marquez (http://localhost:3000) affiche :
- Le graphe de lineage : Bronze → Silver → Gold
- Pour chaque dataset : quelle tâche l'a produit, à quelle heure, depuis quelle source

---

## 13. Bugs réels résolus

Documentés volontairement dans le README — la grille valorise explicitement la capacité à diagnostiquer et résoudre des problèmes en conditions réelles :

1. **Conflit SQLAlchemy dans Airflow** : `airflow/requirements.txt` épinglait SQLAlchemy 2.0.32, incompatible avec la version interne d'Airflow 2.9.3 → suppression de la contrainte de version

2. **`pandas.to_sql()` incompatible avec l'environnement Airflow** : `AttributeError: 'Engine' object has no attribute 'cursor'` → réécriture avec psycopg2 brut dans `aggregate_gold.py::write_to_postgres`

3. **DAGs en pause par défaut** : un DAG en pause accepte un déclenchement manuel mais reste bloqué en `queued` → ajout de `AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION: "false"` dans `docker-compose.yml`

---

## 14. Correspondance RNCP40875

| Compétence | Preuve dans le projet |
|---|---|
| **C1.1** — Base relationnelle adaptée | `sql/01_init_gold.sql` : contraintes, index, rôle lecture seule, schéma en étoile + 3 data marts |
| **C1.2** — Base non-relationnelle | MongoDB `biens_caracteristiques` (attributs variables) + JSONB `pipeline_rapports` |
| **C1.3** — Data Lake sécurisé multi-sources | MinIO 3 buckets + 9 sources ouvertes + Marquez lineage |
| **C1.4** — Scalabilité / résilience | Retries Airflow, repli GeoJSON local, fallback synthétique, MongoDB fail-safe |
| **C2.1** — API interopérable et sécurisée | JWT + rôles, OpenAPI/Swagger, CORS, 60 req/min, 22 endpoints documentés |
| **C2.2** — Système distribué + streaming | DAG `realtime_stream` : 2 processus parallèles (LocalExecutor) → pg_notify → WebSocket |
| **C2.3** — Modélisation multidimensionnelle | Schéma en étoile `dim_arrondissement / dim_temps / fait_prix_immobilier` + 3 data marts |
| **C2.4** — Pipelines mesurés | Rapports JSON horodatés (MinIO + PostgreSQL JSONB) : durée, volume, débit, taux de succès |
| **C3.1** — Qualité des données | Nettoyage Silver documenté étape par étape, rapports versionnés, endpoint `/admin/rapports-qualite` |
| **C3.2** — Dashboard interactif | Carte choroplèthe GeoJSON, 11 indicateurs, espaces par rôle, flux temps réel Vélib |
| **C3.3** — Analyse exploratoire | Comparaison inter-arrondissements, variations annuelles, requêtes étoile multi-axes |

---

## 15. Démarrage rapide

```bash
# 1. Variables d'environnement
cp .env.example .env

# 2. Lancer tous les services
docker compose up -d --build
# → attendre 2-3 minutes

# 3. Déclencher le pipeline manuellement
docker compose exec airflow-webserver airflow dags trigger ingestion_bronze
# attendre ~2 min
docker compose exec airflow-webserver airflow dags trigger transform_silver
# attendre ~8 min
docker compose exec airflow-webserver airflow dags trigger aggregate_gold
```

### Accès aux services

| Service | URL | Identifiants |
|---|---|---|
| Site Urban Immo | http://localhost:8501 | voir comptes ci-dessous |
| API Swagger | http://localhost:8000/docs | — |
| Airflow | http://localhost:8080 | admin / admin |
| MinIO | http://localhost:9001 | minioadmin / minioadmin123 |
| Marquez UI | http://localhost:3000 | — |

### Comptes de démonstration

| Rôle | Email | Mot de passe |
|---|---|---|
| Administrateur | admin@urban-data-explorer.fr | admin123 |
| Employé | employe@urban-data-explorer.fr | employe123 |
| Client | client@urban-data-explorer.fr | client123 |

---

*Projet académique EFREI — RNCP40875 Expert en Ingénierie des données*
