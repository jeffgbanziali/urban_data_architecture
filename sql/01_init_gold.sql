-- sql/01_init_gold.sql
-- Schéma relationnel de la base GOLD (PostgreSQL).
-- Compétences visées : C1.1 (conception relationnelle), C1.2 (JSONB semi-structuré),
-- C2.2 (temps réel + micro-batch), C2.3 (modélisation dimensionnelle en étoile + data marts).

-- ═══════════════════════════════════════════════════════════════
-- ZONE GOLD BATCH (alimentée par le pipeline Airflow)
-- ═══════════════════════════════════════════════════════════════

-- Table plate (rétrocompatibilité API existante — tous les endpoints /prix et /comparaison).
CREATE TABLE IF NOT EXISTS prix_m2_arrondissement (
    arrondissement   SMALLINT NOT NULL CHECK (arrondissement BETWEEN 1 AND 20),
    annee            SMALLINT NOT NULL CHECK (annee BETWEEN 2000 AND 2100),
    prix_m2_median   NUMERIC(10, 2) NOT NULL CHECK (prix_m2_median > 0),
    variation_pct    NUMERIC(6, 2),
    PRIMARY KEY (arrondissement, annee)
);

CREATE TABLE IF NOT EXISTS indicateurs_socio (
    arrondissement   SMALLINT PRIMARY KEY CHECK (arrondissement BETWEEN 1 AND 20),
    -- Source : INSEE — Populations légales 2021 (data.gouv.fr)
    population       INTEGER,
    densite_hab_km2  INTEGER,
    -- Source : WAQI via topic Kafka events.stream (qualite_air_temps_reel)
    indice_qualite_air  NUMERIC(5, 2),
    -- Source : OpenData Paris — espaces verts géocodés (API BAN + point-in-polygon)
    nb_espaces_verts    INTEGER,
    -- Source : SSMSI / Ministère de l'Intérieur — criminalité communale
    taux_criminalite    NUMERIC(8, 2),
    -- Source : OpenData Paris — Vélib' disponibilité temps réel (stations statiques)
    nb_stations_velib   INTEGER,
    -- Source : IDFM / RATP — positions stations réseau RATP (Metro + RER)
    nb_stations_metro   INTEGER
);

-- Ajout idempotent des colonnes si la table existait avant cette migration
DO $$ BEGIN
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='indicateurs_socio' AND column_name='taux_criminalite') THEN
        ALTER TABLE indicateurs_socio ADD COLUMN taux_criminalite NUMERIC(8, 2);
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='indicateurs_socio' AND column_name='nb_stations_velib') THEN
        ALTER TABLE indicateurs_socio ADD COLUMN nb_stations_velib INTEGER;
    END IF;
    IF NOT EXISTS (SELECT 1 FROM information_schema.columns WHERE table_name='indicateurs_socio' AND column_name='nb_stations_metro') THEN
        ALTER TABLE indicateurs_socio ADD COLUMN nb_stations_metro INTEGER;
    END IF;
END $$;

-- ═══════════════════════════════════════════════════════════════
-- SCHÉMA EN ÉTOILE (C2.3 — modélisation multidimensionnelle)
-- Coexiste avec la table plate ; l'API utilise la table plate,
-- ce schéma sert de base aux data marts analytiques.
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS dim_arrondissement (
    arrondissement_id SMALLINT PRIMARY KEY CHECK (arrondissement_id BETWEEN 1 AND 20),
    nom               VARCHAR(30) NOT NULL,
    superficie_km2    NUMERIC(6, 3)
);

CREATE TABLE IF NOT EXISTS dim_temps (
    annee_id SMALLINT PRIMARY KEY CHECK (annee_id BETWEEN 2000 AND 2100),
    annee    SMALLINT NOT NULL
);

-- Table de faits : une ligne par (arrondissement, année).
CREATE TABLE IF NOT EXISTS fait_prix_immobilier (
    arrondissement_id SMALLINT NOT NULL REFERENCES dim_arrondissement(arrondissement_id),
    annee_id          SMALLINT NOT NULL REFERENCES dim_temps(annee_id),
    prix_m2_median    NUMERIC(10, 2) NOT NULL CHECK (prix_m2_median > 0),
    variation_pct     NUMERIC(6, 2),
    nb_transactions   INTEGER,
    PRIMARY KEY (arrondissement_id, annee_id)
);

-- ═══════════════════════════════════════════════════════════════
-- DATA MARTS (C2.3 — vues matérialisées analytiques)
-- Rafraîchies par aggregate_gold.py après chaque run pipeline.
-- Chaque mart combine plusieurs couches de données pour offrir
-- une vision métier directement exploitable.
-- ═══════════════════════════════════════════════════════════════

-- MART 1 : Marché immobilier — prix, variations, segmentation
CREATE MATERIALIZED VIEW IF NOT EXISTS mart_marche_immobilier AS
SELECT
    d.arrondissement_id                             AS arrondissement,
    d.nom                                           AS arrondissement_nom,
    t.annee,
    f.prix_m2_median,
    f.variation_pct,
    f.nb_transactions,
    CASE
        WHEN f.prix_m2_median > 12000 THEN 'premium'
        WHEN f.prix_m2_median > 9000  THEN 'intermediaire'
        ELSE                               'accessible'
    END                                             AS segment_marche,
    CASE
        WHEN f.variation_pct > 5  THEN 'forte_hausse'
        WHEN f.variation_pct > 0  THEN 'hausse'
        WHEN f.variation_pct IS NULL THEN 'inconnu'
        WHEN f.variation_pct > -5 THEN 'baisse'
        ELSE                           'forte_baisse'
    END                                             AS tendance
FROM fait_prix_immobilier f
JOIN dim_arrondissement d ON f.arrondissement_id = d.arrondissement_id
JOIN dim_temps t           ON f.annee_id          = t.annee_id
WITH NO DATA;

-- Index unique nécessaire pour REFRESH CONCURRENTLY
CREATE UNIQUE INDEX IF NOT EXISTS uidx_mart_marche ON mart_marche_immobilier (arrondissement, annee);
CREATE INDEX IF NOT EXISTS idx_mart_marche_segment ON mart_marche_immobilier (segment_marche);

-- Table nécessaire pour mart_mobilite (déclarée ici pour que la vue puisse compiler ;
-- la définition complète avec index reste dans la section TEMPS RÉEL ci-dessous).
CREATE TABLE IF NOT EXISTS velib_agregats_temps_reel (
    arrondissement          SMALLINT PRIMARY KEY CHECK (arrondissement BETWEEN 1 AND 20),
    nb_stations_actives     INTEGER NOT NULL DEFAULT 0,
    velos_disponibles_moyen NUMERIC(6, 2),
    derniere_maj            TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- MART 2 : Mobilité — état Vélib par arrondissement (snapshot courant)
CREATE MATERIALIZED VIEW IF NOT EXISTS mart_mobilite AS
SELECT
    v.arrondissement,
    COALESCE(d.nom, v.arrondissement::text)         AS arrondissement_nom,
    v.nb_stations_actives,
    v.velos_disponibles_moyen,
    v.derniere_maj,
    CASE
        WHEN v.velos_disponibles_moyen < 2  THEN 'critique'
        WHEN v.velos_disponibles_moyen < 5  THEN 'tendu'
        ELSE                                     'normal'
    END                                             AS etat_mobilite
FROM velib_agregats_temps_reel v
LEFT JOIN dim_arrondissement d ON v.arrondissement = d.arrondissement_id
WITH NO DATA;

CREATE UNIQUE INDEX IF NOT EXISTS uidx_mart_mobilite ON mart_mobilite (arrondissement);

-- MART 3 : Qualité de vie — score composite par arrondissement
CREATE MATERIALIZED VIEW IF NOT EXISTS mart_qualite_vie AS
SELECT
    s.arrondissement,
    COALESCE(d.nom, s.arrondissement::text)         AS arrondissement_nom,
    s.population,
    s.densite_hab_km2,
    s.indice_qualite_air,
    s.nb_espaces_verts,
    -- Espaces verts pour 10 000 habitants (indicateur OMS normalisé)
    CASE
        WHEN s.population > 0 AND s.nb_espaces_verts IS NOT NULL
        THEN ROUND(s.nb_espaces_verts::numeric / s.population * 10000, 2)
        ELSE NULL
    END                                             AS espaces_verts_pour_10k_hab,
    -- Score qualité de l'air : 0 (mauvais) à 100 (excellent) selon CAQI
    CASE
        WHEN s.indice_qualite_air IS NULL  THEN NULL
        WHEN s.indice_qualite_air <= 25    THEN 'bon'
        WHEN s.indice_qualite_air <= 50    THEN 'moyen'
        WHEN s.indice_qualite_air <= 75    THEN 'mauvais'
        ELSE                                    'tres_mauvais'
    END                                             AS niveau_qualite_air
FROM indicateurs_socio s
LEFT JOIN dim_arrondissement d ON s.arrondissement = d.arrondissement_id
WITH NO DATA;

CREATE UNIQUE INDEX IF NOT EXISTS uidx_mart_qualite_vie ON mart_qualite_vie (arrondissement);

-- Fonction de rafraîchissement atomique des trois data marts.
-- Appelée par aggregate_gold.py à la fin de chaque run pipeline.
CREATE OR REPLACE FUNCTION refresh_data_marts() RETURNS void
LANGUAGE plpgsql AS $$
BEGIN
    REFRESH MATERIALIZED VIEW CONCURRENTLY mart_marche_immobilier;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mart_mobilite;
    REFRESH MATERIALIZED VIEW CONCURRENTLY mart_qualite_vie;
END;
$$;

-- ═══════════════════════════════════════════════════════════════
-- OBSERVABILITÉ PIPELINE (C1.2 — JSONB, remplace MongoDB)
-- Rapport qualité de chaque run (bronze / silver / gold).
-- Métriques scalaires indexées + payload complet en JSONB.
-- Même capacité de filtrage que MongoDB ($lt taux_succes, filtre stage)
-- via des requêtes SQL standard.
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS pipeline_rapports (
    id                   BIGSERIAL PRIMARY KEY,
    stage                VARCHAR(10) NOT NULL CHECK (stage IN ('bronze', 'silver', 'gold')),
    run_started          TIMESTAMPTZ NOT NULL DEFAULT now(),
    duree_s              NUMERIC(10, 3),
    volume_octets        BIGINT,
    debit_lignes_par_s   NUMERIC(10, 2),
    debit_octets_par_s   NUMERIC(10, 2),
    taux_succes_pct      NUMERIC(5, 2),
    -- Rapport complet (structure libre par stage) — requêtes ad hoc via ->
    payload              JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS idx_pipeline_rapports_stage_date
    ON pipeline_rapports (stage, run_started DESC);
CREATE INDEX IF NOT EXISTS idx_pipeline_rapports_taux
    ON pipeline_rapports (taux_succes_pct);

-- ═══════════════════════════════════════════════════════════════
-- ZONE TEMPS RÉEL — Qualité de l'air (topic events.stream)
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS qualite_air_temps_reel (
    id              BIGSERIAL PRIMARY KEY,
    arrondissement  SMALLINT NOT NULL CHECK (arrondissement BETWEEN 1 AND 20),
    indice_qualite_air NUMERIC(5, 2) NOT NULL,
    horodatage      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_qualite_air_arr_horodatage
    ON qualite_air_temps_reel (arrondissement, horodatage DESC);

-- ═══════════════════════════════════════════════════════════════
-- ZONE TEMPS RÉEL — Disponibilité Vélib (topic mobilite.raw)
-- Source : OpenData Paris (sans clé API, mise à jour chaque minute)
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS disponibilite_velib_temps_reel (
    id              BIGSERIAL PRIMARY KEY,
    arrondissement  SMALLINT NOT NULL CHECK (arrondissement BETWEEN 1 AND 20),
    station_code    VARCHAR(20) NOT NULL,
    station_nom     VARCHAR(255),
    velos_disponibles INTEGER NOT NULL CHECK (velos_disponibles >= 0),
    bornes_libres   INTEGER NOT NULL CHECK (bornes_libres >= 0),
    horodatage      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_velib_arr_horodatage
    ON disponibilite_velib_temps_reel (arrondissement, horodatage DESC);

-- Agrégat glissant par arrondissement (mise à jour incrémentale via UPSERT).
CREATE TABLE IF NOT EXISTS velib_agregats_temps_reel (
    arrondissement          SMALLINT PRIMARY KEY CHECK (arrondissement BETWEEN 1 AND 20),
    nb_stations_actives     INTEGER NOT NULL DEFAULT 0,
    velos_disponibles_moyen NUMERIC(6, 2),
    derniere_maj            TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ═══════════════════════════════════════════════════════════════
-- MICRO-BATCH Vélib (C2.2 — fenêtres tumbling de 10 secondes)
-- ═══════════════════════════════════════════════════════════════

CREATE TABLE IF NOT EXISTS agregats_micro_batch (
    id              BIGSERIAL PRIMARY KEY,
    arrondissement  SMALLINT NOT NULL CHECK (arrondissement BETWEEN 1 AND 20),
    fenetre_debut   TIMESTAMPTZ NOT NULL,
    fenetre_fin     TIMESTAMPTZ NOT NULL,
    nb_stations     INTEGER NOT NULL DEFAULT 0,
    velos_moyen     NUMERIC(6, 2),
    UNIQUE (arrondissement, fenetre_debut)
);

CREATE INDEX IF NOT EXISTS idx_micro_batch_arr_fenetre
    ON agregats_micro_batch (arrondissement, fenetre_debut DESC);

-- ═══════════════════════════════════════════════════════════════
-- SÉCURITÉ : rôle lecture seule pour l'API (moindre privilège)
-- ═══════════════════════════════════════════════════════════════

CREATE INDEX IF NOT EXISTS idx_prix_m2_arr ON prix_m2_arrondissement (arrondissement);

DO $$
BEGIN
    IF NOT EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = 'gold_readonly') THEN
        CREATE ROLE gold_readonly LOGIN PASSWORD 'readonly_pass';
    END IF;
END
$$;

GRANT CONNECT ON DATABASE gold TO gold_readonly;
GRANT USAGE ON SCHEMA public TO gold_readonly;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO gold_readonly;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO gold_readonly;
