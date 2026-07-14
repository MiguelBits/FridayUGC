package com.miguelbits.fridayugc

import com.miguelbits.fridayugc.model.Screen
import com.miguelbits.fridayugc.model.ScreenElement
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class OutcomeVerifierTest {

    @Test
    fun swipe_verified_when_screen_changes() {
        val before = Screen(
            app = "com.instagram.android",
            elements = listOf(ScreenElement(id = 1, text = "Reel 1")),
        )
        val after = before.copy(elements = listOf(ScreenElement(id = 2, text = "Reel 2")))
        val beforeFp = ScreenValidator.fingerprint(before)
        val afterFp = ScreenValidator.fingerprint(after)
        val result = OutcomeVerifier.verify("swipe", true, before, after, beforeFp, afterFp)
        assertEquals("verified", result.status)
        assertTrue(result.changeScore > 0f)
    }

    @Test
    fun tap_unverified_when_screen_unchanged() {
        val screen = Screen(
            app = "com.instagram.android",
            elements = listOf(ScreenElement(id = 1, text = "Like")),
        )
        val fp = ScreenValidator.fingerprint(screen)
        val result = OutcomeVerifier.verify("tap", true, screen, screen, fp, fp)
        assertEquals("unverified", result.status)
        assertEquals(0f, result.changeScore, 0.001f)
    }

    @Test
    fun executor_failure_is_failed() {
        val screen = Screen(app = "com.instagram.android", elements = emptyList())
        val fp = ScreenValidator.fingerprint(screen)
        val result = OutcomeVerifier.verify("tap", false, screen, screen, fp, fp)
        assertEquals("failed", result.status)
    }

    @Test
    fun open_app_verified_on_instagram_foreground() {
        val before = Screen(app = "com.android.launcher", elements = emptyList())
        val after = Screen(app = "com.instagram.android", elements = emptyList())
        val result = OutcomeVerifier.verify(
            "open_app",
            true,
            before,
            after,
            ScreenValidator.fingerprint(before),
            ScreenValidator.fingerprint(after),
        )
        assertEquals("verified", result.status)
    }
}
