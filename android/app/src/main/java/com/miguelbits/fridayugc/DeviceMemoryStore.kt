package com.miguelbits.fridayugc

import android.content.Context
import android.database.sqlite.SQLiteDatabase
import com.miguelbits.fridayugc.model.DeviceMemoryEntry
import com.miguelbits.fridayugc.model.DeviceMemorySyncRequest
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonPrimitive
import java.time.Instant

/** Local cache of learned tap targets; synced to brain after verified steps. */
class DeviceMemoryStore(context: Context) {
    private val db: SQLiteDatabase =
        context.openOrCreateDatabase("friday_device_memory", Context.MODE_PRIVATE, null)

    init {
        db.execSQL(
            """
            CREATE TABLE IF NOT EXISTS device_memory (
                ui_key TEXT PRIMARY KEY,
                x INTEGER NOT NULL,
                y INTEGER NOT NULL,
                resource_hint TEXT NOT NULL,
                success_count INTEGER NOT NULL,
                fail_count INTEGER NOT NULL,
                last_verified_at TEXT NOT NULL,
                ig_version TEXT NOT NULL
            )
            """.trimIndent(),
        )
    }

    /**
     * Record a verified/failed tap.
     *
     * @param resolvedXY when params carried target_id (not x,y), pass the element
     *   center from the accessibility tree so learning stores usable coords instead of 0,0.
     */
    fun bump(
        action: String,
        params: Map<String, JsonElement>,
        verified: String,
        igVersion: String = "",
        resolvedXY: Pair<Int, Int>? = null,
        screenW: Int = 0,
        screenH: Int = 0,
    ) {
        val uiKey = uiKeyFor(action, params) ?: return
        if (uiKey == "comments_icon") return // always anchored below live reel-like — do not memorize
        val paramX = (params["x"] as? JsonPrimitive)?.content?.toIntOrNull() ?: 0
        val paramY = (params["y"] as? JsonPrimitive)?.content?.toIntOrNull() ?: 0
        val x = if (paramX > 0) paramX else resolvedXY?.first ?: 0
        val y = if (paramY > 0) paramY else resolvedXY?.second ?: 0
        val targetId = (params["target_id"] as? JsonPrimitive)?.content.orEmpty()
        val now = Instant.now().toString()
        val success = verified == "verified"
        // Never poison the store with a 0,0 "success" — memory would return a broken
        // hit on next boot. Failures without coords still count for fail_count.
        if (success && (x <= 0 || y <= 0)) return
        db.execSQL(
            """
            INSERT INTO device_memory(ui_key, x, y, resource_hint, success_count, fail_count, last_verified_at, ig_version)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(ui_key) DO UPDATE SET
                x = CASE WHEN excluded.x > 0 THEN excluded.x ELSE device_memory.x END,
                y = CASE WHEN excluded.y > 0 THEN excluded.y ELSE device_memory.y END,
                resource_hint = CASE WHEN excluded.resource_hint != '' THEN excluded.resource_hint ELSE device_memory.resource_hint END,
                success_count = device_memory.success_count + excluded.success_count,
                fail_count = device_memory.fail_count + excluded.fail_count,
                last_verified_at = excluded.last_verified_at,
                ig_version = excluded.ig_version
            """.trimIndent(),
            arrayOf(
                uiKey,
                x,
                y,
                targetId,
                if (success) 1 else 0,
                if (success) 0 else 1,
                now,
                igVersion,
            ),
        )
    }

    /**
     * Overwrite the local memory with entries pulled from the brain. Used at session
     * start so cold-start on a fresh install / cleared cache still has memory hits.
     */
    fun upsertMany(entries: List<DeviceMemoryEntry>) {
        val now = Instant.now().toString()
        db.beginTransaction()
        try {
            for (e in entries) {
                if (e.uiKey.isBlank() || e.x <= 0 || e.y <= 0) continue
                db.execSQL(
                    """
                    INSERT INTO device_memory(ui_key, x, y, resource_hint, success_count, fail_count, last_verified_at, ig_version)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(ui_key) DO UPDATE SET
                        x = excluded.x,
                        y = excluded.y,
                        resource_hint = CASE WHEN excluded.resource_hint != '' THEN excluded.resource_hint ELSE device_memory.resource_hint END,
                        success_count = MAX(device_memory.success_count, excluded.success_count),
                        fail_count = MIN(device_memory.fail_count, excluded.fail_count),
                        last_verified_at = excluded.last_verified_at,
                        ig_version = CASE WHEN excluded.ig_version != '' THEN excluded.ig_version ELSE device_memory.ig_version END
                    """.trimIndent(),
                    arrayOf(
                        e.uiKey,
                        e.x,
                        e.y,
                        e.resourceHint,
                        maxOf(e.successCount, 1),
                        e.failCount,
                        e.lastVerifiedAt.ifBlank { now },
                        e.igVersion,
                    ),
                )
            }
            db.setTransactionSuccessful()
        } finally {
            db.endTransaction()
        }
    }

    suspend fun hydrateFromBrain(brain: BrainClient, deviceId: String) {
        val remote = runCatching { brain.getDeviceMemory(deviceId) }.getOrNull() ?: return
        if (remote.entries.isNotEmpty()) upsertMany(remote.entries)
    }

    fun lookup(uiKey: String): Pair<Int, Int>? {
        val rows = db.rawQuery(
            "SELECT x, y, success_count, fail_count FROM device_memory WHERE ui_key = ? ORDER BY success_count DESC LIMIT 1",
            arrayOf(uiKey),
        )
        rows.use {
            if (!it.moveToFirst()) return null
            val x = it.getInt(0)
            val y = it.getInt(1)
            val success = it.getInt(2)
            val fail = it.getInt(3)
            if (success < 1 || fail > success * 2) return null
            if (x <= 0 || y <= 0) return null
            return x to y
        }
    }

    fun invalidate(uiKey: String) {
        db.delete("device_memory", "ui_key = ?", arrayOf(uiKey))
    }

    fun topEntries(limit: Int = 32): List<DeviceMemoryEntry> {
        val rows = db.rawQuery(
            "SELECT * FROM device_memory ORDER BY success_count DESC LIMIT ?",
            arrayOf(limit.toString()),
        )
        val out = ArrayList<DeviceMemoryEntry>()
        rows.use {
            while (it.moveToNext()) {
                out.add(
                    DeviceMemoryEntry(
                        deviceId = "",
                        uiKey = it.getString(0),
                        x = it.getInt(1),
                        y = it.getInt(2),
                        resourceHint = it.getString(3),
                        successCount = it.getInt(4),
                        failCount = it.getInt(5),
                        lastVerifiedAt = it.getString(6),
                        igVersion = it.getString(7),
                    ),
                )
            }
        }
        return out
    }

    suspend fun syncToBrain(brain: BrainClient, deviceId: String) {
        val entries = topEntries().map { it.copy(deviceId = deviceId) }
        if (entries.isEmpty()) return
        runCatching {
            brain.syncDeviceMemory(DeviceMemorySyncRequest(deviceId = deviceId, entries = entries))
        }
    }

    private fun uiKeyFor(action: String, params: Map<String, JsonElement>): String? {
        // Explicit hint from IntentResolver wins — one schema across phone + brain:
        //   nav_reels, nav_home, comments_icon, comment_heart, action_like_story
        val explicit = (params["ui_key"] as? JsonPrimitive)?.content?.trim()
        if (!explicit.isNullOrEmpty()) return explicit
        val tab = (params["tab"] as? JsonPrimitive)?.content?.lowercase()
        if (tab != null) return "nav_$tab"
        return when (action) {
            "like_comment" -> "comment_heart"
            "tap", "like", "like_story", "save", "follow" -> "action_$action"
            "navigate" -> "navigate"
            "swipe" -> null // do not learn swipes as pointer targets
            else -> null
        }
    }
}
