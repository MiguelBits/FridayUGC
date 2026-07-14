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

    fun bump(action: String, params: Map<String, JsonElement>, verified: String, igVersion: String = "") {
        val uiKey = uiKeyFor(action, params) ?: return
        val x = (params["x"] as? JsonPrimitive)?.content?.toIntOrNull() ?: 0
        val y = (params["y"] as? JsonPrimitive)?.content?.toIntOrNull() ?: 0
        val targetId = (params["target_id"] as? JsonPrimitive)?.content.orEmpty()
        val now = Instant.now().toString()
        val success = verified == "verified"
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
        val tab = (params["tab"] as? JsonPrimitive)?.content?.lowercase()
        if (tab != null) return "nav_$tab"
        return when (action) {
            "like_comment" -> "comments_icon"
            "tap", "like", "like_story", "save", "follow" -> "action_$action"
            "navigate" -> "navigate"
            "swipe" -> "reels_swipe"
            else -> null
        }
    }
}
