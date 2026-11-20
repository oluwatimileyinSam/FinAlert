ALTER TABLE licenses
    ADD COLUMN redeemed_at INTEGER;

ALTER TABLE activations
    ADD COLUMN activation_token_hash TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_activations_token_hash
    ON activations (activation_token_hash);
