package com.miguelbits.fridayugc

import com.miguelbits.fridayugc.model.Screen
import com.miguelbits.fridayugc.model.ScreenElement
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ReelsTargetFinderTest {

    @Test
    fun picks_third_rail_icon_as_comments() {
        val w = 1080
        val h = 2400
        val screen = Screen(
            app = "com.instagram.android",
            elements = listOf(
                railIcon(0, w, (h * 0.38f).toInt()),
                railIcon(1, w, (h * 0.48f).toInt()),
                railIcon(2, w, (h * 0.58f).toInt()),
                railIcon(3, w, (h * 0.72f).toInt(), text = "share"),
            ),
        )
        val pick = ReelsTargetFinder.findCommentsElement(screen, w, h)
        assertEquals(2, pick?.id)
    }

    @Test
    fun excludes_audio_keywords() {
        val w = 1080
        val h = 2400
        val screen = Screen(
            app = "com.instagram.android",
            elements = listOf(
                railIcon(0, w, (h * 0.58f).toInt(), text = "original audio"),
            ),
        )
        assertTrue(ReelsTargetFinder.findCommentsElement(screen, w, h) == null)
        assertTrue(ReelsTargetFinder.commentsTapParams(screen, w, h) == null)
    }

    @Test
    fun detects_audio_browser() {
        val screen = Screen(
            app = "com.instagram.android",
            elements = listOf(
                ScreenElement(id = 0, text = "Use audio in your reel"),
            ),
        )
        assertTrue(ReelsTargetFinder.isAudioBrowser(screen))
    }

    private fun railIcon(id: Int, w: Int, y: Int, text: String = ""): ScreenElement {
        val size = 96
        val x = (w * 0.88f).toInt()
        return ScreenElement(
            id = id,
            clickable = true,
            x = x,
            y = y,
            w = size,
            h = size,
            text = text,
        )
    }
}
