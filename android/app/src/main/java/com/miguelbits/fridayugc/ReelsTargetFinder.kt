package com.miguelbits.fridayugc

import com.miguelbits.fridayugc.model.Screen

/** Safety zones for Reels vision taps — not used for target finding. */
object ReelsTargetFinder {

    private val RAIL_MIN_X = 0.78f

    fun isAudioZone(x: Int, y: Int, w: Int, h: Int): Boolean =
        w > 0 && h > 0 && x > w * RAIL_MIN_X && y >= h * 0.58f

    fun isAudioBrowser(screen: Screen): Boolean {
        val texts = screen.elements.map { it.text.lowercase() }
        return texts.any { t ->
            t.contains("use audio") || t.contains("audio library") ||
                t.contains("browse audio") || t.contains("original audio") ||
                t.contains("trending audio") || t.contains("saved audio") ||
                (t.contains("audio") && (t.contains("reel") || t.contains("track")))
        }
    }
}
