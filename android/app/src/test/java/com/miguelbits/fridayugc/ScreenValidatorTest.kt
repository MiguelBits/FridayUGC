package com.miguelbits.fridayugc

import com.miguelbits.fridayugc.model.Screen
import com.miguelbits.fridayugc.model.ScreenElement
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotEquals
import org.junit.Assert.assertNull
import org.junit.Test

class ScreenValidatorTest {

    @Test
    fun fingerprint_changes_when_elements_change() {
        val a = Screen(
            app = "com.instagram.android",
            elements = listOf(ScreenElement(id = 1, text = "Like", x = 10, y = 20, w = 30, h = 30)),
        )
        val b = a.copy(elements = listOf(ScreenElement(id = 2, text = "Comment", x = 50, y = 60, w = 30, h = 30)))
        val fa = ScreenValidator.fingerprint(a)
        val fb = ScreenValidator.fingerprint(b)
        assertNotEquals(fa, fb)
    }

    @Test
    fun stale_detects_unchanged_screen() {
        val fp = "abc123"
        assertEquals(true, ScreenValidator.isStale(fp, fp))
        assertEquals(false, ScreenValidator.isStale(fp, "other"))
    }

    @Test
    fun validateTap_rejects_non_instagram() {
        val screen = Screen(app = "com.android.launcher", elements = emptyList())
        assertEquals("foreground is not Instagram", ScreenValidator.validateTap(screen, 100, 200))
    }

    @Test
    fun validateTap_accepts_instagram_coords() {
        val screen = Screen(app = "com.instagram.android", elements = emptyList())
        assertNull(ScreenValidator.validateTap(screen, 100, 200))
    }
}
