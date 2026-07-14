-- Phase 1: BeerCard background asset column (SQLite)
-- Run once against an existing ATLAS database created before this migration.
-- New installs using SQLAlchemy create_all on an empty DB get the column from the model.

ALTER TABLE beers ADD COLUMN beercard_background_url VARCHAR(500);
