package com.miguelbits.fridayugc

import com.miguelbits.fridayugc.model.Screen

/** Detects multi-image carousel posts on the home feed (they steal horizontal swipes). */
object CarouselDetector {

    private val fractionPattern = Regex("""(\d+)\s*/\s*(\d+)""")
    private val ofPattern = Regex("""(?i)(?:photo|image|slide|carousel)\s*\d+\s*of\s*\d+""")

    fun hasCarouselPost(screen: Screen, width: Int, height: Int): Boolean {
        if (width <= 0 || height <= 0) return false
        val bandTop = (height * 0.12f).toInt()
        val bandBottom = (height * 0.88f).toInt()
        for (e in screen.elements) {
            val t = e.text
            if (t.isBlank()) continue
            val lower = t.lowercase()
            val cy = e.y + e.h / 2
            if (cy !in bandTop..bandBottom) continue
            if (lower.contains("carousel")) return true
            if (fractionPattern.containsMatchIn(t)) return true
            if (ofPattern.containsMatchIn(t)) return true
        }
        return false
    }
}
