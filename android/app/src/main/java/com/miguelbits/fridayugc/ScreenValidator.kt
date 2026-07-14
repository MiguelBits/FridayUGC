package com.miguelbits.fridayugc

import com.miguelbits.fridayugc.model.Screen
import java.security.MessageDigest

/** Stale-screen detection and coordinate validation before taps. */
object ScreenValidator {

    private val irreversible = setOf("post", "comment", "dm", "follow", "unfollow")

    fun fingerprint(screen: Screen): String {
        val digest = MessageDigest.getInstance("SHA-256")
        val payload = buildString {
            append(screen.app)
            append("|")
            append(screen.activity)
            append("|")
            screen.elements.take(40).forEach { e ->
                append(e.id)
                append(":")
                append(e.text)
                append("@")
                append(e.x)
                append(",")
                append(e.y)
                append(";")
            }
        }
        return digest.digest(payload.toByteArray()).joinToString("") { "%02x".format(it) }.take(16)
    }

    fun isStale(previous: String?, current: String): Boolean =
        !previous.isNullOrBlank() && previous == current

    fun screenChanged(beforeFp: String, afterFp: String): Boolean =
        beforeFp.isNotBlank() && afterFp.isNotBlank() && beforeFp != afterFp

    fun changeScore(before: Screen, after: Screen, beforeFp: String, afterFp: String): Float {
        if (!screenChanged(beforeFp, afterFp) && before.app == after.app && before.activity == after.activity) {
            return 0f
        }
        val beforeTexts = before.elements.map { it.text.trim().lowercase() }.filter { it.isNotEmpty() }.toSet()
        val afterTexts = after.elements.map { it.text.trim().lowercase() }.filter { it.isNotEmpty() }.toSet()
        val union = beforeTexts union afterTexts
        if (union.isEmpty()) return if (screenChanged(beforeFp, afterFp)) 1f else 0f
        val diff = (beforeTexts - afterTexts).size + (afterTexts - beforeTexts).size
        var score = diff.toFloat() / union.size.toFloat()
        if (before.app != after.app) score = maxOf(score, 0.5f)
        if (before.elements.size != after.elements.size) {
            val sizeDelta = kotlin.math.abs(before.elements.size - after.elements.size)
            score = maxOf(score, sizeDelta.toFloat() / maxOf(before.elements.size, after.elements.size, 1).toFloat())
        }
        return score.coerceIn(0f, 1f)
    }

    fun validateTap(screen: Screen, x: Int, y: Int): String? {
        val dm = screen.elements.firstOrNull()?.let { null }
        if (x <= 0 || y <= 0) return "invalid coordinates"
        val maxX = 5000
        val maxY = 5000
        if (x > maxX || y > maxY) return "coordinates out of bounds"
        if (!screen.app.contains("instagram", ignoreCase = true)) return "foreground is not Instagram"
        return null
    }

    fun needsReobserve(action: String): Boolean = action in irreversible
}
