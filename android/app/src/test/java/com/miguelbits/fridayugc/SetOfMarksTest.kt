package com.miguelbits.fridayugc

import android.graphics.Bitmap
import com.miguelbits.fridayugc.model.Screen
import com.miguelbits.fridayugc.model.ScreenElement
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class SetOfMarksTest {

    @Test
    fun annotate_marks_clickable_elements() {
        val bmp = Bitmap.createBitmap(540, 1200, Bitmap.Config.ARGB_8888)
        val screen = Screen(
            app = "com.instagram.android",
            activity = "Home",
            elements = listOf(
                ScreenElement(id = 0, text = "Reels", clickable = true, x = 100, y = 1100, w = 80, h = 80),
                ScreenElement(id = 1, text = "Like", clickable = true, x = 480, y = 600, w = 40, h = 40),
            ),
        )
        val result = SetOfMarks.annotate(bmp, screen, displayWidth = 1080, displayHeight = 2400)
        assertEquals(2, result.marks.size)
        assertTrue(result.marks[0].markId >= 1)
        result.bitmap.recycle()
        bmp.recycle()
    }
}
