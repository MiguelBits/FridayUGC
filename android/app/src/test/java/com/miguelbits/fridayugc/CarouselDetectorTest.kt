package com.miguelbits.fridayugc

import com.miguelbits.fridayugc.model.Screen
import com.miguelbits.fridayugc.model.ScreenElement
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CarouselDetectorTest {

    @Test
    fun detects_fraction_indicator() {
        val screen = Screen(
            app = "com.instagram.android",
            elements = listOf(
                ScreenElement(id = 0, text = "1/5", y = 900, h = 40, w = 80, x = 500),
            ),
        )
        assertTrue(CarouselDetector.hasCarouselPost(screen, 1080, 2400))
    }

    @Test
    fun ignores_plain_feed_scrollable_without_carousel_text() {
        val screen = Screen(
            app = "com.instagram.android",
            elements = listOf(
                ScreenElement(
                    id = 0,
                    scrollable = true,
                    x = 100,
                    y = 600,
                    w = 880,
                    h = 900,
                ),
            ),
        )
        assertFalse(CarouselDetector.hasCarouselPost(screen, 1080, 2400))
    }

    @Test
    fun ignores_full_screen_reels_scrollable() {
        val screen = Screen(
            app = "com.instagram.android",
            elements = listOf(
                ScreenElement(
                    id = 0,
                    scrollable = true,
                    x = 0,
                    y = 200,
                    w = 1080,
                    h = 2000,
                ),
            ),
        )
        assertFalse(CarouselDetector.hasCarouselPost(screen, 1080, 2400))
    }
}
