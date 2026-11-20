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

    const groups = encoded.match(/.{1,4}/g);
    return `PF-${groups.join("-")}`;
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
    const deviceId =
        typeof body?.device_id === "string" ? body.device_id.trim() : "";

    if (!licenseKey || deviceId.length < 16 || deviceId.length > 200) {
        return jsonResponse({ error: "invalid_activation_request" }, 400);
    }

    const platform = ["macos", "windows"].includes(body?.platform)
        ? body.platform
        : "unknown";

    const licenseHash = await keyedHash(
        env.LICENSE_HASH_SECRET,
        `license:${licenseKey}`,
    );
    const deviceHash = await keyedHash(
        env.LICENSE_HASH_SECRET,
        `device:${deviceId}`,
    );

    const license = await env.DB.prepare(
        `SELECT license_id, status, expires_at
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

    let activation = await env.DB.prepare(
        `SELECT device_hash
         FROM activations
         WHERE license_id = ?`,
    )
        .bind(license.license_id)
        .first();

    if (activation && activation.device_hash !== deviceHash) {
        return jsonResponse({ error: "license_locked_to_another_device" }, 403);
    }

    if (!activation) {
        await env.DB.prepare(
            `INSERT OR IGNORE INTO activations (
                license_id,
                device_hash,
                platform,
                first_activated_at,
                last_validated_at
            ) VALUES (?, ?, ?, ?, ?)`,
        )
            .bind(license.license_id, deviceHash, platform, now, now)
            .run();

        activation = await env.DB.prepare(
            `SELECT device_hash
             FROM activations
             WHERE license_id = ?`,
        )
            .bind(license.license_id)
            .first();
    }

    if (!activation || activation.device_hash !== deviceHash) {
        return jsonResponse({ error: "license_locked_to_another_device" }, 403);
    }

    await env.DB.prepare(
        `UPDATE activations
         SET last_validated_at = ?, platform = ?
         WHERE license_id = ?`,
    )
        .bind(now, platform, license.license_id)
        .run();

    return jsonResponse({ status: "active" });
}

async function createLicense(request, env) {
    if (!isAdmin(request, env)) {
        return jsonResponse({ error: "unauthorized" }, 401);
    }

    if (!env.DB || !env.LICENSE_HASH_SECRET) {
        return jsonResponse({ error: "service_not_configured" }, 503);
    }

    const body = await request.json().catch(() => ({}));
    let expiresAt = null;

    if (body.expires_at !== undefined && body.expires_at !== null) {
        expiresAt = Number(body.expires_at);

        if (!Number.isSafeInteger(expiresAt) || expiresAt <= Math.floor(Date.now() / 1000)) {
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

            if (url.pathname === "/admin/licenses" && request.method === "POST") {
                return await createLicense(request, env);
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
