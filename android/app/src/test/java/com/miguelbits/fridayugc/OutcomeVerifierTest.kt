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

    @Test
    fun open_reels_unverified_when_still_on_home() {
        val screen = Screen(
            app = "com.instagram.android",
            elements = listOf(ScreenElement(id = 1, text = "For you")),
        )
        val fp = ScreenValidator.fingerprint(screen)
        val result = OutcomeVerifier.verify("open_reels", true, screen, screen, fp, fp)
        assertEquals("unverified", result.status)
    }

    @Test
    fun open_reels_verified_when_reels_surface_detected() {
        val screen = Screen(
            app = "com.instagram.android",
            activity = "com.instagram.mainactivity.InstagramMainActivity",
            elements = listOf(ScreenElement(id = 1, text = "Reels, selected")),
        )
        val fp = ScreenValidator.fingerprint(screen)
        val result = OutcomeVerifier.verify("open_reels", true, screen, screen, fp, fp)
        assertEquals("verified", result.status)
    }

    @Test
    fun comments_icon_verified_when_sheet_opens() {
        val before = Screen(app = "com.instagram.android", elements = emptyList())
        val after = Screen(
            app = "com.instagram.android",
            elements = listOf(ScreenElement(id = 0, text = "Add a comment")),
        )
        val beforeFp = ScreenValidator.fingerprint(before)
        val afterFp = ScreenValidator.fingerprint(after)
        val result = OutcomeVerifier.verify(
            "tap",
            true,
            before,
            after,
            beforeFp,
            afterFp,
            mapOf("ui_key" to kotlinx.serialization.json.JsonPrimitive("comments_icon")),
            "clips",
        )
        assertEquals("verified", result.status)
    }

    @Test
    fun comment_heart_verified_on_sheet_without_tree_change() {
        val screen = Screen(
            app = "com.instagram.android",
            elements = listOf(ScreenElement(id = 0, text = "Add a comment")),
        )
        val fp = ScreenValidator.fingerprint(screen)
        val result = OutcomeVerifier.verify(
            "like_comment",
            true,
            screen,
            screen,
            fp,
            fp,
            mapOf("ui_key" to kotlinx.serialization.json.JsonPrimitive("comment_heart")),
            "clips",
        )
        assertEquals("verified", result.status)
    }

    @Test
    fun reels_rail_swipe_verified_on_executor_ok() {
        val screen = Screen(app = "com.instagram.android", elements = emptyList())
        val fp = ScreenValidator.fingerprint(screen)
        val result = OutcomeVerifier.verify(
            "swipe",
            true,
            screen,
            screen,
            fp,
            fp,
            mapOf("zone" to kotlinx.serialization.json.JsonPrimitive("reels_rail")),
        )
        assertEquals("verified", result.status)
    }
}
