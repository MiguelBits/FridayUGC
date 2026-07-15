package com.miguelbits.fridayugc

import com.miguelbits.fridayugc.model.Screen
import com.miguelbits.fridayugc.model.ScreenElement
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ReelsTargetFinderTest {

    @Test
    fun detects_audio_browser() {
        val screen = Screen(
            app = "com.instagram.android",
            elements = listOf(ScreenElement(id = 0, text = "Use audio in your reel")),
        )
        assertTrue(ReelsTargetFinder.isAudioBrowser(screen))
    }

    @Test
    fun is_audio_zone() {
        assertTrue(ReelsTargetFinder.isAudioZone(990, 1500, 1080, 2400))
        assertFalse(ReelsTargetFinder.isAudioZone(540, 1200, 1080, 2400))
    }
}
