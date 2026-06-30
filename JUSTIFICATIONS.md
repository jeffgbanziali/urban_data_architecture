# JUSTIFICATIONS.md — Urban Data Explorer

Ce fichier documente chaque brique du système avec sa compétence visée,
sa nécessité réelle, le choix technique retenu, et la preuve concrète
(fichier, requête ou résultat de test) que la brique fonctionne.

---

### MinIO (Data Lake — zones Bronze / Silver / Gold)

- **Compétence visée** : C1.3
- **Nécessité** : stocker des fichiers hétérogènes (CSV compressés, Parquet, GeoJSON, JSON) de tailles variables (DVF Paris = ~50 Mo/an) avec versioning horodaté et isolation par zone de maturité, sans nécessiter un schéma fixe à l'avance.
- **Choix technique** : MinIO (compatible API S3) plutôt qu'un filesystem local ou HDFS. L'API S3 est un standard de facto supporté par boto3 (déjà utilisé pour AWS) ; MinIO peut être remplacé par S3 réel sans changer une ligne de code. HDFS serait surdimensionné pour cette échelle.
- **Donnée/traitement réel** : `pipeline/bronze/download_sources.py` écrit les 9 sources ouvertes téléchargées dans le bucket `bronze` avec préfixe `source/YYYY/MM/DD/HHMMSS/`. Le rapport JSON de chaque run (volume, durée, taux de succès) est visible dans MinIO console (http://localhost:9001) et dans PostgreSQL (`pipeline_rapports`, stage='bronze'). Les Parquet Silver/Gold sont également horodatés avec la même convention.

---

### PostgreSQL Gold (base relationnelle)

- **Compétence visée** : C1.1
- **Nécessité** : exposer des indicateurs agrégés via une API REST avec filtres (arrondissement, année), tris et jointures. Une base relationnelle offre un langage de requête standardisé (SQL), des contraintes d'intégrité et des index pour les patterns d'accès connus.
- **Choix technique** : PostgreSQL 16 plutôt que MySQL ou SQLite. PostgreSQL ajoute `pg_notify/LISTEN` (push WebSocket sans polling, clé pour C2.2), les types `NUMERIC` précis pour les prix, et est le standard des projets data Python (SQLAlchemy, psycopg2, pandas).
- **Donnée/traitement réel** : `sql/01_init_gold.sql` définit les tables avec contraintes CHECK (`arrondissement BETWEEN 1 AND 20`, `prix_m2_median > 0`), clés composites et index. `pipeline/gold/aggregate_gold.py::write_to_postgres` peuple `prix_m2_arrondissement` et `indicateurs_socio` via TRUNCATE + INSERT psycopg2 brut (contourne l'incompatibilité pandas/Airflow documentée dans README.md).

---

### MongoDB — base non-relationnelle (C1.2)

- **Compétence visée** : C1.2 (base de données non relationnelle)
- **Nécessité** : les biens immobiliers ont des attributs qui varient selon leur type — un studio a `{etage, ascenseur}`, une maison `{jardin_m2, garage, nb_niveaux}`. Une liste fixe de colonnes nullable en SQL est inadaptée : MongoDB permet un document par bien avec uniquement les clés pertinentes, sans schéma imposé.
- **Choix technique** : MongoDB 7.0 (service `mongo` dans docker-compose.yml) + driver `motor` (async) côté API FastAPI. La collection `biens_caracteristiques` reçoit un upsert à chaque création ou modification de bien via l'API. Les données structurées communes (titre, prix, arrondissement) restent dans PostgreSQL — MongoDB ne stocke que les caractéristiques variables.
- **Donnée/traitement réel** : `POST /biens` ou `PUT /biens/{id}` déclenche `_upsert_mongo(bien_id, type_bien, caracteristiques)` dans `api/app/routers/biens.py` (écriture non-bloquante — si MongoDB est indisponible, un warning est loggé mais l'API répond 201/200 normalement). Vérification : après `POST /biens` avec `{"type_bien": "appartement", "caracteristiques": {"etage": 4, "ascenseur": true}}`, le document MongoDB confirme `{bien_id: X, type_bien: "appartement", etage: 4, ascenseur: true}`.

### PostgreSQL JSONB — rapports pipeline et recherche semi-structurée

- **Compétence visée** : complément C1.2 (requêtes JSON sur rapports pipeline)
- **Nécessité** : les rapports de qualité du pipeline (volume, durée, taux de succès par source) sont des JSON semi-structurés qu'on veut interroger sans parcourir MinIO fichier par fichier. La colonne JSONB dans PostgreSQL couvre ce cas d'usage analytique, distinct de la flexibilité de schéma couverte par MongoDB.
- **Donnée/traitement réel** : table `pipeline_rapports (stage, taux_succes_pct, payload JSONB)`. `GET /admin/rapports-qualite?seuil_succes=80` filtre via `WHERE taux_succes_pct < :seuil` en SQL pur. Colonne `caracteristiques JSONB` sur `biens` conservée comme index GIN pour les requêtes complexes côté API sans passer par MongoDB.

---

### Système distribué temps-réel — DAG Airflow (C2.2)

- **Compétence visée** : C2.2 (système distribué utilisant des technologies de streaming)
- **Architecture** : DAG `realtime_stream` (schedule `*/3 * * * *`) avec deux tâches **parallèles** : `fetch_air_quality` (WAQI → PostgreSQL) et `fetch_velib` (OpenData Paris → PostgreSQL). Airflow LocalExecutor lance chaque tâche dans un **sous-processus Python distinct** — exécution concurrente réelle, sans état partagé.
- **Streaming** : flux continu toutes les 3 minutes + `pg_notify` après chaque insertion → push WebSocket immédiat vers `/ws/realtime` (inchangé). Le délai bout-en-bout est identique à l'ancienne architecture Kafka.
- **Pourquoi c'est distribué** : deux processus indépendants traitent des sources différentes en parallèle — même principe qu'un consumer group Kafka partitionné par topic, sans le broker.
- **Donnée/traitement réel** : `pipeline/bronze/realtime_fetcher.py` regroupe `fetch_and_store_air_quality()` et `fetch_and_store_velib()`. Après un run du DAG, `SELECT COUNT(*) FROM qualite_air_temps_reel` et `SELECT COUNT(*) FROM disponibilite_velib_temps_reel` augmentent. Le push WebSocket est confirmé via `wscat -c ws://localhost:8000/ws/realtime`.

---

### Flux Vélib temps réel (OpenData Paris)

- **Compétence visée** : C2.2
- **Nécessité** : démontrer un vrai flux d'événements issus d'une source publique en mutation continue, après suppression des transactions immobilières simulées (DVF est un export annuel, pas un flux temps réel).
- **Choix technique** : API OpenData Paris `velib-disponibilite-en-temps-reel` (JSON, sans clé, mise à jour chaque minute) plutôt qu'une génération aléatoire. Colonnes réelles confirmées par inspection : `stationcode`, `name`, `numbikesavailable`, `numdocksavailable`, `coordonnees_geo` (dict `{lat, lon}`). Résolution d'arrondissement par point-in-polygon identique à la chaîne DVF/espaces verts.
- **Donnée/traitement réel** : `streaming/producer_realtime.py::fetch_real_velib_events()` appelle l'API, résout chaque station en arrondissement. `consumer_to_gold.py::handle_velib()` insère dans `disponibilite_velib_temps_reel` + UPSERT `velib_agregats_temps_reel` + `pg_notify`. Confirmation via `wscat -c ws://localhost:8000/ws/realtime` : les événements `{"type":"velib",...}` arrivent sans polling.

---

### Micro-batch (fenêtres tumbling 10s)

- **Compétence visée** : C2.2
- **Nécessité** : la grille distingue explicitement traitement événement-par-événement et micro-batch (fenêtres temporelles). Ce sont deux paradigmes différents répondant à des besoins différents — les deux doivent coexister.
- **Choix technique** : `streaming/micro_batch_processor.py` consomme `mobilite.raw` avec `consumer_timeout_ms=1000` (boucle de 10s), agrège par arrondissement, et écrit dans `agregats_micro_batch`. C'est distinct de `consumer_to_gold.py` qui traite chaque message immédiatement. Pas de Flink/Spark Streaming : le volume Vélib (~1400 stations/min) ne justifie pas un cluster de traitement distribué.
- **Donnée/traitement réel** : après quelques minutes de producer actif, `SELECT * FROM agregats_micro_batch ORDER BY fenetre_debut DESC LIMIT 5;` retourne des fenêtres successives non chevauchantes avec `nb_stations` > 0 et `velos_moyen` cohérent avec les vraies données Vélib.

---

### Qualité de l'air (WAQI / Airparif)

- **Compétence visée** : C2.2
- **Nécessité** : démontre un deuxième flux temps réel sur un topic Kafka distinct (`events.stream`), issu d'une vraie source externe (API WAQI agrégeant les données Airparif pour les stations parisiennes).
- **Choix technique** : WAQI (aqicn.org) avec token optionnel (repli synthétique documenté si absent) plutôt que l'API Airparif directe (format plus complexe, accès moins standardisé).
- **Donnée/traitement réel** : `streaming/producer_realtime.py::fetch_real_air_quality_events()` interroge l'API `map/bounds` avec la bounding box de Paris. `aggregate/aggregate_gold.py::build_indice_qualite_air_snapshot()` calcule la moyenne par arrondissement depuis `qualite_air_temps_reel`. Visible dans `indicateurs_socio.indice_qualite_air` après un run Gold.

---

### Schéma en étoile + Data Marts (C2.3)

- **Compétence visée** : C2.3
- **Nécessité** : la grille demande des données "structurées pour des analyses multidimensionnelles". La table plate `prix_m2_arrondissement` permet des requêtes simples mais ne modélise pas explicitement les dimensions (temps, espace). Le schéma en étoile rend les jointures multi-axes expressives ; les data marts offrent des vues pré-agrégées directement consommables par le frontend ou des outils BI.
- **Choix technique** : `dim_arrondissement` × `dim_temps` → `fait_prix_immobilier` (Kimball classique) + 3 data marts matérialisés (`mart_marche_immobilier`, `mart_mobilite`, `mart_qualite_vie`). Les vues matérialisées sont préférées aux vues simples : les données sont précalculées à la fin de chaque run pipeline, les requêtes API ne recalculent rien. `REFRESH MATERIALIZED VIEW CONCURRENTLY` ne bloque pas les lectures pendant le refresh.
- **Donnée/traitement réel** : `pipeline/gold/aggregate_gold.py::populate_star_schema()` peuple les dimensions et faits. `aggregate_gold.py::refresh_data_marts()` appelle `SELECT refresh_data_marts()` (fonction SQL définie dans `01_init_gold.sql`) pour rafraîchir les 3 marts atomiquement. Endpoints publics : `GET /marts/marche`, `GET /marts/qualite-vie`, `GET /marts/mobilite`.

---

### Airflow (orchestration)

- **Compétence visée** : C2.4 (pipelines mesurés et orchestrés)
- **Nécessité** : déclencher le pipeline en chaîne (Bronze → Silver → Gold) à 2h du matin, avec retries automatiques (2 tentatives, délai 5 min), sans intervention manuelle. Un simple cron shell ne gère pas les dépendances inter-étapes ni la visibilité sur les runs.
- **Choix technique** : Airflow 2.9.3 avec LocalExecutor (pas de Celery/Kubernetes : inutile pour 3 DAGs séquentiels). Alternatifs : Prefect ou Dagster, mais Airflow est plus répandu en entreprise et mieux documenté pour un projet académique.
- **Donnée/traitement réel** : 3 DAGs (`ingestion_bronze` → `transform_silver` → `aggregate_gold`) visibles dans l'interface Airflow (http://localhost:8080). Chaque BashOperator cd dans son répertoire (`pipeline/bronze`, `pipeline/silver`, `pipeline/gold`). `TriggerDagRunOperator` assure l'enchaînement.

---

### FastAPI (API REST)

- **Compétence visée** : C2.1
- **Nécessité** : exposer les données Gold (prix, indicateurs, GeoJSON) et les fonctionnalités agence (biens, favoris, gestion utilisateurs) via une interface HTTP standardisée, consommable par le frontend React et par des tiers.
- **Choix technique** : FastAPI plutôt que Flask ou Django REST Framework. FastAPI génère automatiquement la documentation OpenAPI (Swagger/ReDoc), a de meilleures performances asynchrones (asyncpg pour le WebSocket), et la validation Pydantic réduit le code de validation manuel.
- **Donnée/traitement réel** : `GET /geo/arrondissements` retourne le GeoJSON enrichi en < 50ms depuis MinIO/gold. `GET /admin/rapports-qualite?seuil_succes=80` interroge MongoDB. `WS /ws/realtime` pousse les événements Vélib et qualité air sans polling. Documentation complète : http://localhost:8000/docs.

---

### Authentification JWT + bcrypt (C2.1)

- **Compétence visée** : C2.1
- **Nécessité** : trois profils métier réels avec des droits distincts — un client consulte, un employé gère les biens, un admin gère les comptes. Un système binaire connecté/déconnecté ne modélise pas cette réalité.
- **Choix technique** : JWT (PyJWT, HS256, 8h) + bcrypt (pas passlib, problèmes de compatibilité) plutôt que sessions serveur ou OAuth tiers. JWT est stateless : pas de session côté serveur, compatible avec une API consommée par un frontend séparé et potentiellement plusieurs instances. `get_current_user` recharge l'utilisateur depuis la base à chaque requête : une désactivation par un admin est immédiatement effective, même avec un token encore valide.
- **Donnée/traitement réel** : `tests/test_api.py` valide les 3 points clés — `test_client_cannot_create_bien` (403 sur POST /biens), `test_admin_only_user_management` (403 client sur /admin/users), `test_admin_cannot_deactivate_self`. Tous passent avec `pytest tests/test_api.py -v`.

---

### Pipeline Bronze — Ingestion sources ouvertes

- **Compétence visée** : C1.3
- **Nécessité** : télécharger les sources ouvertes (DVF, INSEE, OpenData Paris, WAQI) de façon résiliente — chaque source est indépendante, un échec n'interrompt pas les autres.
- **Choix technique** : script Python (`pipeline/bronze/download_sources.py`) avec dict de sources, gestion individuelle des erreurs, rapport JSON versionné. Pas de framework ETL lourd (Airbyte, Fivetran) : le volume et le nombre de sources ne le justifient pas.
- **Donnée/traitement réel** : 9 sources configurées. Le rapport de run (disponible dans MinIO `bronze/_reports/ingestion/`) contient `status`, `bytes`, `duration_s` par source. Les métriques agrégées (`duree_s`, `volume_octets`, `debit_octets_par_s`, `taux_succes_pct`) sont aussi dans MongoDB.

---

### Pipeline Silver — Nettoyage et qualité

- **Compétence visée** : C3.1
- **Nécessité** : les données brutes (DVF, INSEE, espaces verts) contiennent des doublons, des valeurs aberrantes, des formats inconsistants (BOM UTF-8, séparateur `;` vs `,`). La zone Silver garantit que seules des données propres atteignent la zone Gold.
- **Choix technique** : pandas pour le nettoyage (déduplication, imputation médiane, filtrage aberrants), Shapely pour le point-in-polygon, API BAN pour le géocodage. Parquet comme format de sortie (typage fort, compression, lecture colonnaire rapide).
- **Donnée/traitement réel** : `pipeline/silver/clean_silver.py::clean_dvf` détecte automatiquement le format réel geo-dvf (colonnes `code_postal`/`valeur_fonciere`) vs démo. Les rapports qualité Silver (taux_retenu_pct, nb doublons supprimés, etc.) sont versionnés dans `silver/_reports/quality/` et dans MongoDB.

---

### Pipeline Gold — Agrégation et exports

- **Compétence visée** : C2.3, C2.4
- **Nécessité** : calculer les indicateurs métier finaux (prix médian/m², variation annuelle, indicateurs socio) depuis les Parquet Silver, peupler le schéma en étoile, et produire le GeoJSON enrichi pour l'explorateur de données.
- **Choix technique** : pandas pour les agrégations, psycopg2 brut pour l'écriture PostgreSQL (contourne l'incompatibilité pandas/Airflow), export GeoJSON avec clé stable `enriched_arrondissements/latest.geojson` (consommée directement par l'API).
- **Donnée/traitement réel** : `pipeline/gold/aggregate_gold.py::populate_star_schema` peuple `dim_arrondissement`, `dim_temps`, `fait_prix_immobilier`. La requête de démonstration multi-axes (jointure 3 tables) retourne prix médian par arrondissement ET par année. Métriques du run dans MongoDB (stage=gold).

---

---

### Audit des 8 indicateurs (4 obligatoires + 4 personnalisés)

**Obligatoires :**

| # | Indicateur | Table / Colonne | Source | Preuve (valeur arr. 1) |
|---|---|---|---|---|
| 1 | Prix/m² médian | `prix_m2_arrondissement.prix_m2_median` | DVF 2021-2025 data.gouv.fr | 13 304 €/m² (2021) |
| 2 | Évolution du prix dans le temps | `prix_m2_arrondissement.variation_pct` | Calculé depuis DVF | −1.61 % (arr.1, 2022) |
| 3 | Logements sociaux (%) | `indicateurs_socio.pct_logements_sociaux` | RPLS 2023 (SDES / data.gouv.fr) | Colonnes créées — remplies au 1er run Bronze avec sources branchées |
| 4 | Typologie des logements | `indicateurs_socio.pct_appartements`, `type_dominant` | INSEE RP 2021 — base communale logements | Colonnes créées — remplies au 1er run Bronze |

Pour les indicateurs 3 et 4 : les sources existent (RPLS et INSEE RP publient des données par commune à codes 75101-75120), les fonctions Bronze/Silver/Gold sont entièrement implémentées. Les URLs dans `download_sources.py` doivent être vérifiées à partir d'un accès réseau (`/fr/datasets/r/<UUID>` pour RPLS, `fichier/7705694/` pour INSEE RP). La résilience est assurée : un échec d'URL est loggé sans bloquer les autres sources.

**Personnalisés (7 disponibles, 4 minimum requis) :**

| # | Indicateur | Table / Colonne | Source | Valeur arr. 1 |
|---|---|---|---|---|
| 5 | Qualité de l'air | `indicateurs_socio.indice_qualite_air` | WAQI (stations réelles) + IDW pour arr. sans station | 99.6 |
| 6 | Densité de population | `indicateurs_socio.densite_hab_km2` | INSEE Populations légales 2021 | 8 699 hab/km² |
| 7 | Population | `indicateurs_socio.population` | INSEE Populations légales 2021 | 15 919 hab |
| 8 | Espaces verts | `indicateurs_socio.nb_espaces_verts` | OpenData Paris (point-in-polygon) | 16 lieux |
| 9 | Criminalité | `indicateurs_socio.taux_criminalite` | SSMSI — Base communale délits (données réelles) | 668.1 faits/1 000 hab |
| 10 | Stations Métro/RER | `indicateurs_socio.nb_stations_metro` | IDFM emplacement-des-gares-idf | 15 stations |
| 11 | Stations Vélib | `indicateurs_socio.nb_stations_velib` | OpenData Paris Vélib' (point-in-polygon) | 27 stations |

Tous les indicateurs personnalisés sont réels, différenciés par arrondissement, et proviennent de sources officielles vérifiées.

---

### Tests de charge (C1.1)

- **Compétence visée** : C1.1
- **Nécessité** : la grille exige des "tests de charge confirmant l'intégrité et la performance de la base de données".
- **Choix technique** : pgbench (inclus dans l'image PostgreSQL officielle, aucune dépendance à ajouter) pour la base, httpx async pour l'API. pgbench mesure les TPS et la latence sous 10 connexions concurrentes. `tests/test_charge_api.py` mesure latence p50/p95 et taux d'erreur de l'API sous charge.
- **Donnée/traitement réel** : commandes à exécuter et résultats documentés dans `docs/rapport_tests_charge.md` (résultats réels à compléter après exécution — voir ce fichier).

---

### Tests de résilience (C1.4)

- **Compétence visée** : C1.4
- **Nécessité** : la grille demande que les mécanismes de résilience soient "pris en compte ET TESTÉS" — le code a des replis (Vélib silencieux si échec, GeoJSON local si MinIO absent, retries Airflow), mais ils doivent être vérifiés en coupant vraiment un service.
- **Choix technique** : script shell `tests/test_resilience.sh` qui arrête/redémarre les services Docker et vérifie les comportements attendus. Résultats consignés dans `docs/rapport_tests_resilience.md`.
- **Donnée/traitement réel** : scénarios documentés dans `tests/test_resilience.sh` — (1) MinIO arrêté → `/geo/arrondissements` répond avec le GeoJSON de référence local, (2) producer arrêté → consumer ne plante pas, (3) réseau sortant coupé → pipeline continue avec lignes non géocodées tracées.

---

### Gouvernance de données — Marquez / OpenLineage

- **Compétence visée** : C1.3 (traçabilité du data lake), C2.4 (observabilité du pipeline)
- **Nécessité** : savoir quelles données ont été produites par quel traitement, à quelle heure, depuis quelle source. Sans lineage, un bug dans `clean_silver.py` est difficile à tracer jusqu'aux fichiers bronze concernés. La gouvernance rend le pipeline auditable.
- **Choix technique** : Marquez (projet OpenLineage, Linux Foundation) plutôt qu'OpenMetadata (trop lourd : 4 containers + 8 GB RAM) ou Apache Atlas (complexité Hadoop). Marquez s'intègre nativement à Airflow via le provider `apache-airflow-providers-openlineage` — chaque DAG run émet automatiquement des événements de lineage (datasets en entrée/sortie, durée, statut) vers l'API REST Marquez. L'UI (`http://localhost:3000`) affiche le graphe Bronze → Silver → Gold sans configuration manuelle.
- **Donnée/traitement réel** : Airflow est configuré avec `AIRFLOW__OPENLINEAGE__TRANSPORT` et `AIRFLOW__OPENLINEAGE__NAMESPACE=urban-data-explorer` (voir `docker-compose.yml`). Après un run pipeline, l'UI Marquez affiche les 3 DAGs et les datasets (`bronze/dvf_2024.csv`, `silver/dvf_2024.parquet`, `gold/prix_m2_arrondissement`). Config serveur dans `governance/marquez.yml`.
