const encoder = new TextEncoder();
const KEY_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789";

function jsonResponse(data, status = 200) {
    return new Response(JSON.stringify(data), {
        status,
        headers: { "Content-Type": "application/json; charset=utf-8" },
    });
}

function normalizeLicenseKey(value) {
    if (typeof value !== "string") {
        return null;
    }

    const compact = value.toUpperCase().replace(/[\s-]/g, "");

    if (!/^PF[A-HJ-NP-Z2-9]{26}$/.test(compact)) {
        return null;
    }

    return compact;
}

function normalizeActivationToken(value) {
    if (
        typeof value !== "string"
        || !/^[A-Za-z0-9_-]{40,200}$/.test(value)
    ) {
        return null;
    }

    return value;
}

function generateLicenseKey() {
    const bytes = crypto.getRandomValues(new Uint8Array(16));
    let buffer = 0;
    let bits = 0;
    let encoded = "";

    for (const byte of bytes) {
        buffer = (buffer << 8) | byte;
        bits += 8;

        while (bits >= 5) {
            bits -= 5;
            encoded += KEY_ALPHABET[(buffer >> bits) & 31];
        }
    }

    if (bits > 0) {
        encoded += KEY_ALPHABET[(buffer << (5 - bits)) & 31];
    }

    return `PF-${encoded.match(/.{1,4}/g).join("-")}`;
}

async function keyedHash(secret, value) {
    const key = await crypto.subtle.importKey(
        "raw",
        encoder.encode(secret),
        { name: "HMAC", hash: "SHA-256" },
        false,
        ["sign"],
    );

    const signature = await crypto.subtle.sign(
        "HMAC",
        key,
        encoder.encode(value),
    );

    return Array.from(new Uint8Array(signature))
        .map((byte) => byte.toString(16).padStart(2, "0"))
        .join("");
}

function isAdmin(request, env) {
    const expected = env.LICENSE_ADMIN_TOKEN;
    const supplied = request.headers.get("Authorization") || "";

    return Boolean(expected) && supplied === `Bearer ${expected}`;
}

async function activateLicense(request, env) {
    if (!env.DB || !env.LICENSE_HASH_SECRET) {
        return jsonResponse({ error: "service_not_configured" }, 503);
    }

    const body = await request.json().catch(() => null);
    const licenseKey = normalizeLicenseKey(body?.license_key);
    const activationToken = normalizeActivationToken(body?.activation_token);
    const deviceId =
        typeof body?.device_id === "string" ? body.device_id.trim() : "";

    if (
        !licenseKey
        || !activationToken
        || deviceId.length < 16
        || deviceId.length > 200
    ) {
        return jsonResponse({ error: "invalid_activation_request" }, 400);
    }

    const platform = ["macos", "windows"].includes(body?.platform)
        ? body.platform
        : "unknown";

    const licenseHash = await keyedHash(
        env.LICENSE_HASH_SECRET,
        `license:${licenseKey}`,
    );
    const activationTokenHash = await keyedHash(
        env.LICENSE_HASH_SECRET,
        `activation:${activationToken}`,
    );
    const deviceHash = await keyedHash(
        env.LICENSE_HASH_SECRET,
        `device:${deviceId}`,
    );

    const license = await env.DB.prepare(
        `SELECT license_id, status, expires_at, redeemed_at
         FROM licenses
         WHERE key_hash = ?`,
    )
        .bind(licenseHash)
        .first();

    if (!license || license.status !== "active") {
        return jsonResponse({ error: "license_not_valid" }, 403);
    }

    const now = Math.floor(Date.now() / 1000);

    if (license.expires_at !== null && license.expires_at <= now) {
        return jsonResponse({ error: "license_expired" }, 403);
    }

    if (license.redeemed_at !== null) {
        const existing = await env.DB.prepare(
            `SELECT device_hash, activation_token_hash
             FROM activations
             WHERE license_id = ?`,
        )
            .bind(license.license_id)
            .first();

        if (
            existing
            && existing.device_hash === deviceHash
            && existing.activation_token_hash === activationTokenHash
        ) {
            return jsonResponse({
                status: "active",
                license_id: license.license_id,
            });
        }

        if (existing && existing.device_hash !== deviceHash) {
            return jsonResponse(
                { error: "license_locked_to_another_device" },
                403,
            );
        }

        return jsonResponse({ error: "license_already_redeemed" }, 409);
    }

    await env.DB.batch([
        env.DB.prepare(
            `INSERT OR IGNORE INTO activations (
                license_id,
                device_hash,
                activation_token_hash,
                platform,
                first_activated_at,
                last_validated_at
            )
            SELECT license_id, ?, ?, ?, ?, ?
            FROM licenses
            WHERE license_id = ?
              AND status = 'active'
              AND redeemed_at IS NULL`,
        ).bind(
            deviceHash,
            activationTokenHash,
            platform,
            now,
            now,
            license.license_id,
        ),
        env.DB.prepare(
            `UPDATE licenses
             SET redeemed_at = ?
             WHERE license_id = ?
               AND status = 'active'
               AND redeemed_at IS NULL
               AND EXISTS (
                   SELECT 1
                   FROM activations
                   WHERE license_id = ?
                     AND device_hash = ?
                     AND activation_token_hash = ?
               )`,
        ).bind(
            now,
            license.license_id,
            license.license_id,
            deviceHash,
            activationTokenHash,
        ),
    ]);

    const claimed = await env.DB.prepare(
        `SELECT
            a.device_hash,
            a.activation_token_hash,
            l.license_id,
            l.redeemed_at
         FROM activations AS a
         INNER JOIN licenses AS l ON l.license_id = a.license_id
         WHERE l.license_id = ?`,
    )
        .bind(license.license_id)
        .first();

    if (
        claimed
        && claimed.device_hash === deviceHash
        && claimed.activation_token_hash === activationTokenHash
        && claimed.redeemed_at !== null
    ) {
        return jsonResponse({
            status: "active",
            license_id: license.license_id,
        });
    }

    if (claimed && claimed.device_hash !== deviceHash) {
        return jsonResponse(
            { error: "license_locked_to_another_device" },
            403,
        );
    }

    return jsonResponse({ error: "license_already_redeemed" }, 409);
}

async function validateActivation(request, env) {
    if (!env.DB || !env.LICENSE_HASH_SECRET) {
        return jsonResponse({ error: "service_not_configured" }, 503);
    }

    const body = await request.json().catch(() => null);
    const activationToken = normalizeActivationToken(body?.activation_token);
    const deviceId =
        typeof body?.device_id === "string" ? body.device_id.trim() : "";

    if (
        !activationToken
        || deviceId.length < 16
        || deviceId.length > 200
    ) {
        return jsonResponse({ error: "invalid_validation_request" }, 400);
    }

    const tokenHash = await keyedHash(
        env.LICENSE_HASH_SECRET,
        `activation:${activationToken}`,
    );
    const deviceHash = await keyedHash(
        env.LICENSE_HASH_SECRET,
        `device:${deviceId}`,
    );

    const record = await env.DB.prepare(
        `SELECT
            l.license_id,
            l.status,
            l.expires_at,
            a.device_hash
         FROM activations AS a
         INNER JOIN licenses AS l ON l.license_id = a.license_id
         WHERE a.activation_token_hash = ?`,
    )
        .bind(tokenHash)
        .first();

    if (!record || record.status !== "active") {
        return jsonResponse({ error: "activation_not_valid" }, 403);
    }

    if (record.device_hash !== deviceHash) {
        return jsonResponse(
            { error: "activation_locked_to_another_device" },
            403,
        );
    }

    const now = Math.floor(Date.now() / 1000);

    if (record.expires_at !== null && record.expires_at <= now) {
        return jsonResponse({ error: "license_expired" }, 403);
    }

    await env.DB.prepare(
        `UPDATE activations
         SET last_validated_at = ?
         WHERE activation_token_hash = ?`,
    )
        .bind(now, tokenHash)
        .run();

    return jsonResponse({
        status: "active",
        license_id: record.license_id,
    });
}

async function createLicense(request, env) {
    if (!isAdmin(request, env)) {
        return jsonResponse({ error: "unauthorized" }, 401);
    }

    if (!env.DB || !env.LICENSE_HASH_SECRET) {
        return jsonResponse({ error: "service_not_configured" }, 503);
    }

    const body = await request.json().catch(() => ({}));

    if (!body || typeof body !== "object" || Array.isArray(body)) {
        return jsonResponse({ error: "invalid_request" }, 400);
    }

    let expiresAt = null;

    if (body.expires_at !== undefined && body.expires_at !== null) {
        expiresAt = Number(body.expires_at);

        if (
            !Number.isSafeInteger(expiresAt)
            || expiresAt <= Math.floor(Date.now() / 1000)
        ) {
            return jsonResponse({ error: "invalid_expiration" }, 400);
        }
    }

    const licenseKey = generateLicenseKey();
    const licenseHash = await keyedHash(
        env.LICENSE_HASH_SECRET,
        `license:${normalizeLicenseKey(licenseKey)}`,
    );
    const licenseId = crypto.randomUUID();
    const now = Math.floor(Date.now() / 1000);

    await env.DB.prepare(
        `INSERT INTO licenses (
            license_id,
            key_hash,
            status,
            created_at,
            expires_at
        ) VALUES (?, ?, 'active', ?, ?)`,
    )
        .bind(licenseId, licenseHash, now, expiresAt)
        .run();

    return jsonResponse(
        {
            license_key: licenseKey,
            license_id: licenseId,
            expires_at: expiresAt,
        },
        201,
    );
}

async function revokeLicense(request, env) {
    if (!isAdmin(request, env)) {
        return jsonResponse({ error: "unauthorized" }, 401);
    }

    if (!env.DB) {
        return jsonResponse({ error: "service_not_configured" }, 503);
    }

    const body = await request.json().catch(() => null);
    const licenseId =
        typeof body?.license_id === "string" ? body.license_id.trim() : "";

    if (!licenseId) {
        return jsonResponse({ error: "license_id_required" }, 400);
    }

    const license = await env.DB.prepare(
        "SELECT license_id FROM licenses WHERE license_id = ?",
    )
        .bind(licenseId)
        .first();

    if (!license) {
        return jsonResponse({ error: "license_not_found" }, 404);
    }

    await env.DB.prepare(
        "UPDATE licenses SET status = 'revoked' WHERE license_id = ?",
    )
        .bind(licenseId)
        .run();

    return jsonResponse({ status: "revoked" });
}

async function getLicenseStats(request, env) {
    if (!isAdmin(request, env)) {
        return jsonResponse({ error: "unauthorized" }, 401);
    }

    if (!env.DB) {
        return jsonResponse({ error: "service_not_configured" }, 503);
    }

    const stats = await env.DB.prepare(
        `SELECT
            (SELECT COUNT(*) FROM licenses) AS total_licenses,
            (
                SELECT COUNT(*) FROM licenses
                WHERE status = 'active'
                  AND (expires_at IS NULL OR expires_at > ?)
            ) AS valid_licenses,
            (
                SELECT COUNT(*) FROM licenses
                WHERE redeemed_at IS NOT NULL
            ) AS redeemed_licenses,
            (SELECT COUNT(*) FROM activations) AS claimed_devices`,
    )
        .bind(Math.floor(Date.now() / 1000))
        .first();

    return jsonResponse(stats);
}

export default {
    async fetch(request, env) {
        const url = new URL(request.url);

        try {
            if (url.pathname === "/health" && request.method === "GET") {
                return jsonResponse({ status: "ok" });
            }

            if (url.pathname === "/api/activate" && request.method === "POST") {
                return await activateLicense(request, env);
            }

            if (url.pathname === "/api/validate" && request.method === "POST") {
                return await validateActivation(request, env);
            }

            if (url.pathname === "/admin/licenses" && request.method === "POST") {
                return await createLicense(request, env);
            }

            if (
                url.pathname === "/admin/licenses/revoke"
                && request.method === "POST"
            ) {
                return await revokeLicense(request, env);
            }

            if (url.pathname === "/admin/stats" && request.method === "GET") {
                return await getLicenseStats(request, env);
            }

            return jsonResponse({ error: "not_found" }, 404);
        } catch {
            return jsonResponse({ error: "server_error" }, 500);
        }
    },
};
