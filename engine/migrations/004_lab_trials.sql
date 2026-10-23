-- PLAN_V2 V2-6: explicit research provenance columns on lab_trials
ALTER TABLE lab_trials ADD COLUMN prereg_id TEXT;
ALTER TABLE lab_trials ADD COLUMN data_hash TEXT;
ALTER TABLE lab_trials ADD COLUMN post_hoc INTEGER DEFAULT 0;
