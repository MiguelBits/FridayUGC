package com.miguelbits.fridayugc

import com.miguelbits.fridayugc.model.Screen
import com.miguelbits.fridayugc.model.ScreenElement
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ScreenClassifierTest {

    @Test
    fun home_feed_when_for_you_visible() {
        val screen = Screen(
            app = "com.instagram.android",
            elements = listOf(
                ScreenElement(id = 0, text = "For you", clickable = true),
                ScreenElement(id = 1, text = "Reels", clickable = true, y = 2000, h = 48),
            ),
        )
        val state = ScreenClassifier.classify(screen)
        assertEquals("home_feed", state.screenType)
        assertEquals("home", state.selectedTab)
        assertTrue(state.confidence >= 0.85f)
    }

    @Test
    fun sparse_scrollable_without_reels_signals_is_home_feed() {
        val screen = Screen(
            app = "com.instagram.android",
            elements = listOf(
                ScreenElement(id = 0, role = "scrollable", scrollable = true, w = 400, h = 800, y = 200),
            ),
        )
        val state = ScreenClassifier.classify(screen)
        assertEquals("home_feed", state.screenType)
        assertTrue(state.needsVision)
    }

    @Test
    fun comments_sheet_detected() {
        val screen = Screen(
            app = "com.instagram.android",
            elements = listOf(ScreenElement(id = 0, text = "Add a comment…", editable = true)),
        )
        val state = ScreenClassifier.classify(screen)
        assertEquals("comments_sheet", state.screenType)
    }

    @Test
    fun not_instagram_needs_vision() {
        val screen = Screen(app = "com.android.launcher", elements = emptyList())
        val state = ScreenClassifier.classify(screen)
        assertEquals("other_app", state.screenType)
        assertTrue(state.needsVision)
    }

    @Test
    fun likely_reels_without_home_tabs() {
        val screen = Screen(
            app = "com.instagram.android",
            elements = listOf(
                ScreenElement(id = 0, role = "scrollable", scrollable = true, w = 400, h = 800, y = 200),
                ScreenElement(id = 1, text = "Reels, selected", clickable = true, y = 2100),
            ),
        )
        val state = ScreenClassifier.classify(screen)
        assertEquals("reels_viewer", state.screenType)
        assertTrue(ScreenClassifier.likelyReelsSurface(state, screen))
    }

    @Test
    fun sparseScrollableAloneIsNotLikelyReels() {
        val screen = Screen(
            app = "com.instagram.android",
            elements = listOf(
                ScreenElement(id = 0, role = "scrollable", scrollable = true, w = 400, h = 800, y = 200),
            ),
        )
        val state = ScreenClassifier.classify(screen)
        assertFalse(ScreenClassifier.likelyReelsSurface(state, screen))
    }

    @Test
    fun story_viewer_from_activity() {
        val screen = Screen(app = "com.instagram.android", elements = emptyList())
        val state = ScreenClassifier.classify(screen, activityClass = "com.instagram.story.viewer.StoryViewerActivity")
        assertEquals("story_viewer", state.screenType)
    }

    @Test
    fun home_feed_warns_story_tray() {
        val screen = Screen(
            app = "com.instagram.android",
            elements = listOf(
                ScreenElement(id = 0, text = "Your story", clickable = true, y = 120),
                ScreenElement(id = 1, text = "For you", clickable = true),
            ),
        )
        val state = ScreenClassifier.classify(screen)
        assertEquals("home_feed", state.screenType)
        assertTrue(state.signals.any { it.contains("story tray") })
    }
}
