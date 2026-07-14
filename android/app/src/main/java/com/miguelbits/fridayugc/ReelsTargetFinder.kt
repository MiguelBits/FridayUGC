package com.miguelbits.fridayugc

import com.miguelbits.fridayugc.model.Screen
import com.miguelbits.fridayugc.model.ScreenElement
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonPrimitive

/** Picks Reels right-rail icons without hitting like, share, or audio. */
object ReelsTargetFinder {

    private val COMMENTS_Y = 0.58f
    private val RAIL_X = 0.92f
    private val REEL_LIKE_Y_MAX = 0.54f
    private val COMMENTS_Y_MIN = 0.54f
    private val COMMENTS_Y_MAX = 0.64f
    private val RAIL_MIN_X = 0.78f
    private val AUDIO_Y_MIN = 0.68f

    private val blockedKeywords = listOf(
        "audio", "music", "sound", "song", "artist", "original",
        "share", "send", "repost", "remix", "more", "options",
        "save", "follow", "following", "profile", "like", "heart",
    )

    fun commentsTapParams(screen: Screen, w: Int, h: Int): Map<String, JsonElement>? {
        val el = findCommentsElement(screen, w, h) ?: return null
        return mapOf("target_id" to JsonPrimitive(el.id))
    }

    fun findCommentsElement(screen: Screen, w: Int, h: Int): ScreenElement? {
        if (w <= 0 || h <= 0) return null
        val labeled = screen.elements.filter { e ->
            e.clickable && e.w in 1..160 && e.h in 1..160 &&
                e.text.lowercase().let { t ->
                    (t.contains("comment") && !t.contains("commentary")) ||
                        t.contains("id:comment")
                }
        }
        labeled.minByOrNull { kotlin.math.abs((it.y + it.h / 2) - h * COMMENTS_Y) }?.let { return it }

        val railIcons = screen.elements.filter { isRailIcon(it, w, h) }
            .sortedBy { it.y + it.h / 2 }
        railIcons.firstOrNull { e ->
            val cy = e.y + e.h / 2
            cy >= h * COMMENTS_Y_MIN && cy <= h * COMMENTS_Y_MAX
        }?.let { return it }
        if (railIcons.size >= 3) {
            // profile → like → comments (3rd icon)
            return railIcons[2]
        }
        return null
    }

    fun isAudioBrowser(screen: Screen): Boolean {
        val texts = screen.elements.map { it.text.lowercase() }
        return texts.any { t ->
            t.contains("use audio") || t.contains("audio library") ||
                t.contains("browse audio") || t.contains("original audio") ||
                (t.contains("audio") && t.contains("reel"))
        }
    }

    private fun isRailIcon(e: ScreenElement, w: Int, h: Int): Boolean {
        if (!e.clickable || e.w <= 0 || e.h <= 0) return false
        if (e.w > 180 || e.h > 180) return false
        val cx = e.x + e.w / 2
        val cy = e.y + e.h / 2
        if (cx < w * RAIL_MIN_X) return false
        if (cy < h * 0.35f || cy > h * AUDIO_Y_MIN) return false
        val t = e.text.lowercase()
        if (blockedKeywords.any { t.contains(it) }) return false
        return true
    }
}
