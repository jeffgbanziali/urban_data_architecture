# Urban Immo — Urban Data Explorer

Projet académique EFREI (RNCP40875 — Expert en Ingénierie des données) :
une agence immobilière parisienne fictive dont le site web et les outils
internes sont pilotés par une architecture data complète (Bronze/Silver/Gold,
streaming temps réel, orchestration Airflow, API sécurisée par rôles).

## Vue d'ensemble

```
Sources ouvertes (DVF, INSEE, OpenData Paris, Airparif)
        │
        ▼
  Ingestion Python  ──────────────►  Zone BRONZE (MinIO, horodaté)
        │                                   │
        │                            DAG transform_silver (Airflow)
        │                                   ▼
        │                            Zone SILVER (MinIO, Parquet nettoyé)
        │                                   │
        │                            DAG aggregate_gold (Airflow)
        │                                   ▼
        │                       Zone GOLD : PostgreSQL + exports MinIO
        │                                   │
  Kafka (transactions temps réel) ──────────┤
        │                                   ▼
        └──────────────────────────►   API FastAPI (JWT, rôles, OpenAPI)
                                            │
                                            ▼
                          Frontend React (vitrine agence + espaces par rôle
                                + explorateur de données interactif)
```

## Démarrage rapide

```bash
cp .env.example .env          # adapter si besoin (mots de passe de démo)
docker compose up -d --build  # build + démarrage de tous les services
```

Premier démarrage : compter 2-3 minutes (build des images, migrations Airflow,
scripts SQL d'initialisation). Une fois prêt :

| Service | URL | Identifiants |
|---|---|---|
| Site Urban Immo (front React) | http://localhost:8501 | voir comptes démo ci-dessous |
| API (documentation Swagger) | http://localhost:8000/docs | — |
| Console MinIO (data lake) | http://localhost:9001 | minioadmin / minioadmin123 |
| Interface Airflow | http://localhost:8080 | admin / admin |
| PostgreSQL Gold | localhost:5432 | gold_user / gold_pass |

Pour déclencher manuellement le pipeline complet (sinon il tourne tous les
jours à 2h du matin) :

```bash
make pipeline
# ou directement :
docker compose exec airflow-webserver airflow dags trigger ingestion_bronze
```

## Comptes de démonstration

Créés automatiquement par `sql/02_init_auth.sql` au premier démarrage :

| Rôle | Email | Mot de passe |
|---|---|---|
| Administrateur | admin@urban-data-explorer.fr | admin123 |
| Employé | employe@urban-data-explorer.fr | employe123 |
| Client | client@urban-data-explorer.fr | client123 |

**⚠️ Mots de passe de démonstration uniquement — à changer avant toute mise en production.**

## Droits d'accès par rôle

| Rôle | Peut faire |
|---|---|
| **Client** | Consulter les biens publics, gérer ses favoris, voir les tendances de prix de ses arrondissements favoris. Auto-inscription possible (`/inscription`). |
| **Employé** | Tout ce qu'un client peut consulter, + créer/modifier des biens, accéder à l'explorateur de données complet. Compte créé uniquement par un admin. |
| **Administrateur** | Tout ce qu'un employé peut faire, + gérer les comptes utilisateurs (création, rôle, activation/désactivation), + supprimer des biens. |

L'authentification utilise des JWT (8h de validité par défaut). Chaque
requête sur un endpoint protégé recharge l'utilisateur depuis la base : un
compte désactivé par un administrateur perd l'accès immédiatement, même avec
un token encore valide.

## Structure du dépôt

```
pipeline/
  bronze/       Ingestion sources ouvertes -> zone Bronze (MinIO)
  silver/       Nettoyage, validation qualité, géocodage -> zone Silver
  gold/         Agrégations métier, schéma en étoile -> PostgreSQL Gold + MinIO
streaming/      Kafka producer (qualité air WAQI + Vélib OpenData Paris temps réel)
                consumer_to_gold.py (événement-par-événement) +
                micro_batch_processor.py (fenêtres tumbling 10s)
airflow/        DAGs d'orchestration (ingestion_bronze, transform_silver, aggregate_gold)
api/            API FastAPI (auth JWT, biens, favoris, admin, data Gold, MongoDB)
frontend/       Site React (vitrine agence, espaces par rôle, explorateur de données)
sql/            DDL PostgreSQL (schéma plat + étoile + tables streaming)
tests/          Tests pytest (pipeline data + API, charge, résilience)
```

## API — Endpoints, rôles et quotas (C2.1)

**Quota général : 60 req/min par IP** (reverse-proxy en production).
Un quota différencié par rôle n'est pas appliqué : les endpoints intensifs sont
déjà protégés par authentification — voir `JUSTIFICATIONS.md` entrée C2.1.

| Endpoint | Rôle requis | Quota | Description |
|---|---|---|---|
| `POST /auth/register` | public | 60/min | Créer un compte client |
| `POST /auth/login` | public | 60/min | Obtenir un token JWT |
| `GET /auth/me` | client+ | 60/min | Profil courant |
| `GET /biens` | public | 60/min | Liste biens (filtres) |
| `GET /biens/{id}` | public | 60/min | Détail d'un bien |
| `GET /biens/{id}/caracteristiques` | public | 60/min | Attributs libres (MongoDB) |
| `POST /biens` | employe / admin | 60/min | Créer un bien |
| `PUT /biens/{id}` | employe / admin | 60/min | Modifier un bien |
| `DELETE /biens/{id}` | admin | 60/min | Supprimer un bien |
| `GET /arrondissements` | public | 60/min | Indicateurs socio |
| `GET /prix` | public | 60/min | Prix médian/m² par année |
| `GET /timeline` | public | 60/min | Évolution historique |
| `GET /comparaison` | public | 60/min | Comparaison 2 arrondissements |
| `GET /geo/arrondissements` | public | 60/min | GeoJSON enrichi (carte) |
| `WS /ws/realtime` | public | — | Push qualité air + Vélib |
| `GET /favoris` | client+ | 60/min | Mes favoris |
| `POST /favoris/{id}` | client+ | 60/min | Ajouter un favori |
| `DELETE /favoris/{id}` | client+ | 60/min | Retirer un favori |
| `GET /admin/users` | admin | 60/min | Lister tous les comptes |
| `POST /admin/users` | admin | 60/min | Créer un employé/admin |
| `PATCH /admin/users/{id}/role` | admin | 60/min | Changer le rôle |
| `PATCH /admin/users/{id}/active` | admin | 60/min | Activer/désactiver |
| `GET /admin/rapports-qualite` | admin | 60/min | Runs pipeline (MongoDB) |
| `GET /admin/metriques-pipeline` | admin | 60/min | Évolution métriques |

## Lancer les tests sans Docker

Les tests utilisent une base SQLite éphémère (aucune dépendance à PostgreSQL
ou MinIO) pour valider rapidement la logique de nettoyage des données, le
géocodage (API BAN simulée + point-in-polygon réel), la construction du
GeoJSON enrichi et le comportement de l'API (authentification, rôles, CRUD) :

```bash
make test
# ou :
pip install -r requirements-dev.txt -r api/requirements.txt
pytest tests/ -v
```

Un fichier supplémentaire (`tests/test_realtime_integration.py`) valide le
mécanisme de push temps réel (agrégat glissant + `LISTEN`/`NOTIFY`
PostgreSQL), qui nécessite un vrai serveur PostgreSQL (SQLite ne supporte pas
`LISTEN`/`NOTIFY`). Il est **automatiquement ignoré (skip)** si aucun
PostgreSQL n'est accessible — la commande `make test` ci-dessus reste donc
toujours utilisable sans Docker. Pour l'exécuter réellement :

```bash
docker compose up -d postgres-gold
POSTGRES_GOLD_HOST=localhost pytest tests/test_realtime_integration.py -v
```

## Bugs réels rencontrés et corrigés lors du premier déploiement

Trois bugs ont été détectés en déployant le projet en conditions réelles
(Docker Desktop / Windows), au-delà de ce qui était testable en isolation.
Les garder documentés ici est volontaire — savoir expliquer une difficulté
rencontrée et comment elle a été résolue est explicitement valorisé dans la
grille d'évaluation :

1. **Conflit de version SQLAlchemy dans le conteneur Airflow.** `airflow/requirements.txt`
   épinglait `SQLAlchemy==2.0.32`, alors qu'Airflow 2.9.3 embarque sa propre
   version (figée, non substituable sans casser son ORM interne). Résultat :
   `sqlalchemy.exc.ArgumentError` au démarrage du scheduler. Corrigé en
   retirant cette ligne — nos scripts n'utilisent que `create_engine`/`text()`,
   compatibles avec n'importe quelle version.
2. **`pandas.DataFrame.to_sql()` incompatible avec l'environnement Airflow.**
   Même en passant un `Engine` ou une `Connection` SQLAlchemy valide, pandas
   ne les reconnaissait pas dans ce conteneur précis et basculait sur un mode
   de compatibilité supposant une syntaxe SQLite — incompatible avec
   PostgreSQL (`AttributeError: 'Engine' object has no attribute 'cursor'`,
   puis une erreur de syntaxe `?` au lieu de `%s`). Corrigé en écrivant
   l'`INSERT` nous-mêmes via une connexion psycopg2 brute
   (`aggregate_gold.py::write_to_postgres`), qui contourne entièrement le
   problème de détection de pandas.
3. **DAGs mis en pause par défaut.** Airflow met tout nouveau DAG en pause à
   sa création ; un DAG en pause accepte un déclenchement manuel mais le run
   reste bloqué en `queued` indéfiniment. Corrigé en ajoutant
   `AIRFLOW__CORE__DAGS_ARE_PAUSED_AT_CREATION: "false"` dans `docker-compose.yml`.

## Choix d'architecture et limites assumées

Le pipeline suit fidèlement le schéma d'architecture cible : deux topics
Kafka distincts (`transactions.raw` + `events.stream` pour la qualité de
l'air), géocodage réel (API BAN) avec résolution d'arrondissement par
point-in-polygon sur les géométries officielles, agrégats temps réel
maintenus par UPSERT, push WebSocket par notification PostgreSQL
(`LISTEN`/`NOTIFY`, sans scrutation périodique), et un export GeoJSON enrichi
en zone Gold qui alimente directement l'explorateur de données du frontend.

`ingestion/download_sources.py` télécharge désormais de vraies sources
ouvertes fonctionnelles, validées en déploiement réel (pas seulement en
sandbox) :
  - **espaces_verts** : vrai fichier OpenData Paris (~500 espaces verts,
    coordonnées fournies directement) ; résolution d'arrondissement par
    point-in-polygon réel, avec repli sur le code postal si la coordonnée est
    absente. Voir `transform/clean_silver.py::clean_espaces_verts_real`.
  - **dvf_2021 → dvf_2025** : vrai format geo-dvf (data.gouv.fr), détecté
    automatiquement (présence de `code_postal`/`valeur_fonciere` plutôt que
    `arrondissement`/`prix_m2` déjà calculés) ; seuls les locaux d'habitation
    (Appartement/Maison) sont conservés. Voir `clean_silver.py::clean_dvf`.

Le jeu de données synthétique (`generate_sample_data.py`) reste disponible en
repli automatique si une source réelle est indisponible le jour J (réseau,
changement de format côté fournisseur, site qui bloque l'accès automatisé...).

## Indicateurs de l'explorateur de données

Seuls les indicateurs adossés à une vraie source publique sont exposés dans
l'explorateur — c'est un choix de qualité, pas une régression :

| Indicateur | Source réelle |
|---|---|
| Prix au m² (par année) | DVF / geo-dvf, data.gouv.fr |
| Variation annuelle du prix | Calculée depuis les DVF |
| Population | INSEE — fichier "Communes et villes de France" (data.gouv.fr) |
| Densité (hab/km²) | INSEE — même source |
| Qualité de l'air | WAQI via le topic Kafka `events.stream` (temps réel) |
| Espaces verts géocodés | OpenData Paris + géocodage API BAN + point-in-polygon |

Les indicateurs qui existaient dans une version précédente sous forme
synthétique (`delits_pour_1000_hab`, `revenu_median_annuel`, `taux_chomage`,
`score_transport`, `satisfaction_vie`, etc.) ont été **supprimés entièrement**
plutôt que conservés avec des valeurs inventées.

Améliorations futures possibles (sources identifiées, non encore branchées) :
- `delits_pour_1000_hab` : vraie source SSMSI disponible sur data.gouv.fr
  (fichier national ~38 Mo, schéma complexe, non traité dans cette version).
- `score_transport` / stations : l'API RATP Open Data qui était référencée
  a été dépréciée (dataset supprimé) — à rebrancher si une nouvelle URL
  officielle est publiée.
- `part_logements_sociaux_pct` : données disponibles via les recensements
  INSEE (RP), mais pas encore intégrées dans le pipeline.

Limites encore assumées :

- **Carte schématique pour les indicateurs sans dimension géographique** :
  l'explorateur de données affiche les vraies géométries officielles des
  arrondissements (via `GET /geo/arrondissements`), mais les espaces verts ne
  sont pas individuellement positionnés sur la carte (seul leur comptage par
  arrondissement est exploité).
- **Format geo-dvf non testé contre le fichier exact** : contrairement à
  espaces_verts (validé contre un vrai export utilisateur), l'adaptation au
  vrai format DVF est basée sur le schéma officiel documenté de data.gouv.fr,
  mais n'a pas pu être vérifiée contre un fichier réel téléchargé en direct.
- **Une connexion PostgreSQL dédiée par client WebSocket** (`LISTEN` via
  asyncpg) : simple et fonctionnel à l'échelle de ce projet ; un usage à très
  forte concurrence préfèrerait un unique listener interne avec fan-out vers
  les clients connectés.
- **Jeton API unique (X-API-Key)** en plus du JWT pour certains usages
  internes : pas de rotation de clé ni de refresh token — suffisant pour une
  démonstration, à faire évoluer pour de la production.
- **Limitation de débit en mémoire** : fonctionne pour une instance unique de
  l'API ; un déploiement multi-instances nécessiterait un store partagé
  (Redis).

Le détail complet (sources de données, méthodologie de préparation,
correspondance avec le référentiel de compétences) est disponible dans
[`frontend/public/docs.html`](frontend/public/docs.html), servi à l'adresse
http://localhost:8501/docs.html une fois le projet démarré.

## Correspondance avec le référentiel de compétences (RNCP40875)

| Compétence | Preuve dans le projet |
|---|---|
| C1.1 — Base relationnelle adaptée | `sql/01_init_gold.sql` + `sql/02_init_auth.sql` : contraintes, index, rôle lecture seule, schéma en étoile |
| C1.2 — Base non relationnelle (NoSQL) | MongoDB : `biens_caracteristiques` (attributs variables) + `rapports_qualite_pipeline` ; endpoints `/admin/rapports-qualite`, `/biens/{id}/caracteristiques` |
| C1.3 — Data Lake sécurisé multi-sources | `pipeline/bronze/download_sources.py`, buckets MinIO isolés ; métriques volume/débit sur chaque run |
| C1.4 — Scalabilité / résilience | Sources indépendantes, fallback synthétique, retries Airflow, repli GeoJSON local, repli Vélib silencieux |
| C2.1 — API interopérable et sécurisée | JWT + rôles, OpenAPI, CORS, quotas documentés ; tableau endpoints/rôles/quotas dans ce README |
| C2.2 — Streaming temps réel + micro-batch | Kafka `events.stream` (qualité air) + `mobilite.raw` (Vélib réel) ; `consumer_to_gold.py` (événement) + `micro_batch_processor.py` (fenêtre 10s) |
| C2.3 — Modélisation multidimensionnelle | `pipeline/silver/clean_silver.py` ; `pipeline/gold/aggregate_gold.py` : schéma en étoile `dim_arrondissement / dim_temps / fait_prix_immobilier` |
| C2.4 — Pipelines mesurés | Rapports JSON horodatés (MinIO + MongoDB) avec `duree_s`, `volume_octets`, `debit_lignes_par_s`, `taux_succes_pct` à chaque étape |
| C3.1 — Préparation/qualité des données | Nettoyage documenté étape par étape, rapports de qualité versionnés, interrogeables via `/admin/rapports-qualite` |
| C3.2 — Dashboard interactif et inclusif | Explorateur de données (choroplèthe GeoJSON enrichi), espaces par rôle, vitrine biens, flux temps réel Vélib |
| C3.3 — Analyse exploratoire / insights | Comparaisons arrondissements, variations annuelles, requête étoile multi-axes, indicateurs multi-sources |
