-- sql/init_auth.sql
-- Schéma d'authentification et de gestion métier "agence immobilière".
-- Exécuté automatiquement au premier démarrage du conteneur postgres-gold
-- (docker-entrypoint-initdb.d), juste après init_gold.sql.
--
-- Trois rôles applicatifs (vérifiés côté API, pas seulement côté SQL) :
--   - client   : consulte les biens publics, gère ses favoris, voit les
--                tendances de prix des arrondissements qui l'intéressent.
--   - employe  : gère le portefeuille de biens, consulte l'explorateur de
--                données complet pour conseiller les clients.
--   - admin    : tout ce que peut faire un employé, + gestion des comptes
--                utilisateurs (création, changement de rôle, désactivation).

CREATE TABLE IF NOT EXISTS users (
    id              BIGSERIAL PRIMARY KEY,
    email           VARCHAR(255) UNIQUE NOT NULL,
    hashed_password VARCHAR(255) NOT NULL,
    full_name       VARCHAR(255) NOT NULL,
    role            VARCHAR(20) NOT NULL DEFAULT 'client' CHECK (role IN ('client', 'employe', 'admin')),
    is_active       BOOLEAN NOT NULL DEFAULT TRUE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS biens (
    id              BIGSERIAL PRIMARY KEY,
    titre           VARCHAR(255) NOT NULL,
    description     TEXT,
    arrondissement  SMALLINT NOT NULL CHECK (arrondissement BETWEEN 1 AND 20),
    type_bien       VARCHAR(30) NOT NULL CHECK (type_bien IN ('Studio', 'T2', 'T3', 'T4', 'T5+', 'Maison')),
    prix            NUMERIC(12, 2) NOT NULL CHECK (prix > 0),
    surface_m2      NUMERIC(8, 2) NOT NULL CHECK (surface_m2 > 0),
    photo_url       TEXT,
    statut          VARCHAR(20) NOT NULL DEFAULT 'disponible' CHECK (statut IN ('disponible', 'sous_offre', 'vendu')),
    employe_id      BIGINT REFERENCES users(id) ON DELETE SET NULL,
    -- Attributs variables selon le type de bien (C1.2 — semi-structuré JSONB).
    -- Ex. Studio : {"etage": 3, "ascenseur": false}
    --     Maison : {"jardin_m2": 80, "garage": true, "nb_niveaux": 2}
    -- PostgreSQL JSONB remplace ici MongoDB : même flexibilité de schéma,
    -- indexation GIN, requêtes JSONPath — sans système supplémentaire.
    caracteristiques JSONB NOT NULL DEFAULT '{}'::jsonb,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Index GIN sur JSONB : accélère les requêtes sur les clés/valeurs variables.
CREATE INDEX IF NOT EXISTS idx_biens_caracteristiques ON biens USING GIN (caracteristiques);

CREATE TABLE IF NOT EXISTS favoris (
    client_id       BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    bien_id         BIGINT NOT NULL REFERENCES biens(id) ON DELETE CASCADE,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (client_id, bien_id)
);

CREATE INDEX IF NOT EXISTS idx_biens_arrondissement ON biens (arrondissement);
CREATE INDEX IF NOT EXISTS idx_biens_statut ON biens (statut);
CREATE INDEX IF NOT EXISTS idx_users_role ON users (role);

-- Comptes de démonstration (mots de passe pour la soutenance, À CHANGER en
-- production). Hash bcrypt précalculés, jamais de mot de passe en clair stocké.
--   admin@urban-data-explorer.fr   / admin123    (rôle admin)
--   employe@urban-data-explorer.fr / employe123  (rôle employe)
--   client@urban-data-explorer.fr  / client123   (rôle client)
INSERT INTO users (email, hashed_password, full_name, role) VALUES
    ('admin@urban-data-explorer.fr',   '$2b$12$cTgkrad.L4d/yBzevsf1MehmNLzg5Wa5Q/iAyzdyvOVTnusyxVsui', 'Administrateur Démo', 'admin'),
    ('employe@urban-data-explorer.fr', '$2b$12$KaXMUma.5dEoXAkq94jkMebMXKaHbSvKEZ.D0T4fSEyfpROZ5q/T.', 'Employé Démo',        'employe'),
    ('client@urban-data-explorer.fr',  '$2b$12$1fRNmEBy5AxtrvZlBGC1XeAJfBDR7.Oh2B6RKcL0Ri9MP8TNiUYrm', 'Client Démo',         'client')
ON CONFLICT (email) DO NOTHING;

-- Quelques biens de démonstration pour que la vitrine ne soit pas vide.
INSERT INTO biens (titre, description, arrondissement, type_bien, prix, surface_m2, photo_url, statut, employe_id)
SELECT * FROM (VALUES
    ('Appartement lumineux Marais', 'Beau T2 rénové au cœur du Marais, proche métro.', 3, 'T2', 480000, 45, NULL, 'disponible', (SELECT id FROM users WHERE email='employe@urban-data-explorer.fr')),
    ('Studio étudiant Quartier Latin', 'Studio fonctionnel idéal premier achat ou investissement.', 5, 'Studio', 265000, 22, NULL, 'disponible', (SELECT id FROM users WHERE email='employe@urban-data-explorer.fr')),
    ('Loft familial Bastille', 'T4 atypique avec verrière, quartier Bastille.', 11, 'T4', 690000, 95, NULL, 'sous_offre', (SELECT id FROM users WHERE email='employe@urban-data-explorer.fr')),
    ('Maison de ville Montmartre', 'Maison avec jardin, calme absolu sur la Butte.', 18, 'Maison', 950000, 120, NULL, 'disponible', (SELECT id FROM users WHERE email='employe@urban-data-explorer.fr'))
) AS v(titre, description, arrondissement, type_bien, prix, surface_m2, photo_url, statut, employe_id)
WHERE NOT EXISTS (SELECT 1 FROM biens);

GRANT SELECT ON users, biens, favoris TO gold_readonly;
