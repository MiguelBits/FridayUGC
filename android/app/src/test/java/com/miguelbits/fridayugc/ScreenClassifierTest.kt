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
    fun reels_viewer_sparse_scrollable() {
        val screen = Screen(
            app = "com.instagram.android",
            elements = listOf(
                ScreenElement(id = 0, role = "scrollable", scrollable = true, w = 400, h = 800, y = 200),
            ),
        )
        val state = ScreenClassifier.classify(screen)
        assertEquals("reels_viewer", state.screenType)
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
    fun reels_nav_label_alone_stays_home() {
        val screen = Screen(
            app = "com.instagram.android",
            elements = List(30) { i ->
                ScreenElement(id = i, text = "post $i", clickable = true)
            } + ScreenElement(id = 99, text = "Reels, selected", clickable = true),
        )
        val state = ScreenClassifier.classify(screen)
        assertFalse(state.screenType == "reels_viewer")
    }
}
