CREATE TABLE IF NOT EXISTS licenses (
    license_id TEXT PRIMARY KEY,
    key_hash TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'active'
        CHECK (status IN ('active', 'revoked')),
    created_at INTEGER NOT NULL,
    expires_at INTEGER
);

CREATE TABLE IF NOT EXISTS activations (
    activation_id INTEGER PRIMARY KEY AUTOINCREMENT,
    license_id TEXT NOT NULL
        REFERENCES licenses (license_id) ON DELETE CASCADE,
    device_hash TEXT NOT NULL,
    platform TEXT NOT NULL DEFAULT 'unknown'
        CHECK (platform IN ('macos', 'windows', 'unknown')),
    first_activated_at INTEGER NOT NULL,
    last_validated_at INTEGER NOT NULL,
    UNIQUE (license_id)
);

CREATE INDEX IF NOT EXISTS idx_activations_license_id
    ON activations (license_id);
