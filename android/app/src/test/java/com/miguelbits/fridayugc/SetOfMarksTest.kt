package com.miguelbits.fridayugc

import com.miguelbits.fridayugc.model.Screen
import com.miguelbits.fridayugc.model.ScreenElement
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class SetOfMarksTest {

    @Test
    fun annotate_marks_clickable_elements() {
        val screen = Screen(
            app = "com.instagram.android",
            activity = "Home",
            elements = listOf(
                ScreenElement(id = 0, text = "Reels", clickable = true, x = 100, y = 1100, w = 80, h = 80),
                ScreenElement(id = 1, text = "Like", clickable = true, x = 480, y = 600, w = 40, h = 40),
            ),
        )
        val candidates = SetOfMarks.clickableCandidates(screen)
        val marks = SetOfMarks.computeMarks(
            candidates,
            scaleX = 540f / 1080,
            scaleY = 1200f / 2400,
        )
        assertEquals(2, marks.size)
        assertTrue(marks[0].markId >= 1)
        assertEquals("Reels", marks[0].text)
        assertEquals(0, marks[0].elementId)
    }
}
