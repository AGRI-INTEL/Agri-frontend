-- AgriIntel360 - Initialisation PostgreSQL avec PostGIS
-- Ce script configure la base de données avec les extensions nécessaires

-- Activer l'extension PostGIS pour les données géospatiales
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS postgis_topology;

-- Activer l'extension UUID pour les clés primaires UUID
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Activer l'extension pour les index GIN/GIST
CREATE EXTENSION IF NOT EXISTS pg_trgm;

-- Créer un utilisateur pour l'application si nécessaire
-- L'utilisateur est déjà créé via les variables d'environnement Docker

-- Configurer la timezone par défaut
SET timezone = 'UTC';

-- Créer la base de données pour Airflow
CREATE DATABASE airflow;

-- Créer les schémas
CREATE SCHEMA IF NOT EXISTS public;
CREATE SCHEMA IF NOT EXISTS analytics;
CREATE SCHEMA IF NOT EXISTS ml_models;

-- Créer une table de log système temporaire si elle n'existe pas
CREATE TABLE IF NOT EXISTS public.system_log (
    id SERIAL PRIMARY KEY,
    message TEXT NOT NULL,
    level VARCHAR(20) NOT NULL DEFAULT 'INFO',
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT NOW()
);

-- Accorder les permissions
GRANT USAGE ON SCHEMA public TO postgres;
GRANT USAGE ON SCHEMA analytics TO postgres;
GRANT USAGE ON SCHEMA ml_models TO postgres;

-- Fonction pour mettre à jour automatiquement updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ language 'plpgsql';


-- Index pour les recherches fréquentes
-- Ces index seront créés automatiquement par SQLAlchemy,
-- mais on peut les préparer ici si nécessaire

-- Log des initialisations
INSERT INTO public.system_log (message, level, timestamp) 
VALUES ('Database initialization completed', 'INFO', NOW())
ON CONFLICT DO NOTHING;

COMMENT ON DATABASE agriintel360 IS 'AgriIntel360 - Plateforme de Business Intelligence Agricole';
COMMENT ON SCHEMA public IS 'Schéma principal contenant les tables de données';
COMMENT ON SCHEMA analytics IS 'Schéma pour les vues et tables d''analytics';
COMMENT ON SCHEMA ml_models IS 'Schéma pour stocker les métadonnées des modèles ML';