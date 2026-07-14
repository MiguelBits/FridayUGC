package com.miguelbits.fridayugc

import com.miguelbits.fridayugc.model.Screen
import com.miguelbits.fridayugc.model.ScreenElement
import com.miguelbits.fridayugc.model.ScreenState
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Test

class CommentLikesRoutineTest {

    @Test
    fun open_comments_uses_coord_below_reel_like() {
        val tracker = SessionTracker().apply {
            phase = "reels_comment_likes"
            reelsTabOpened = true
        }
        val screen = Screen(app = "com.instagram.android", elements = emptyList())
        val dm = android.util.DisplayMetrics().apply {
            widthPixels = 1080
            heightPixels = 2400
        }
        val step = CommentLikesRoutine.nextStep(tracker, screen, ScreenState(screenType = "reels_viewer"), dm)
        assertEquals("tap", step?.action)
        val y = (step?.params?.get("y") as? kotlinx.serialization.json.JsonPrimitive)?.content?.toInt()
        assert(y != null && y > 2400 * 0.54 && y < 2400 * 0.65)
    }

    @Test
    fun in_comments_uses_sheet_zone_coords() {
        val tracker = SessionTracker().apply {
            phase = "reels_comment_likes"
            commentsSheetOpen = true
            commentLikesPhase = CommentLikesRoutine.PHASE_IN_COMMENTS
        }
        val screen = Screen(app = "com.instagram.android", elements = emptyList())
        val dm = android.util.DisplayMetrics().apply {
            widthPixels = 1080
            heightPixels = 2400
        }
        val step = CommentLikesRoutine.nextStep(tracker, screen, ScreenState(screenType = "comments_sheet"), dm)
        assertEquals("like_comment", step?.action)
        val y = (step?.params?.get("y") as? kotlinx.serialization.json.JsonPrimitive)?.content?.toInt()
        assert(y != null && y >= 2400 * 0.55)
    }

    @Test
    fun next_reel_swipes_on_rail_zone() {
        val tracker = SessionTracker().apply {
            phase = "reels_comment_likes"
            reelsTabOpened = true
            readyForNextReel = true
        }
        val step = CommentLikesRoutine.nextStep(
            tracker,
            Screen(app = "com.instagram.android", elements = emptyList()),
            ScreenState(screenType = "reels_viewer"),
            android.util.DisplayMetrics().apply { widthPixels = 1080; heightPixels = 2400 },
        )
        assertEquals("swipe", step?.action)
        assertEquals("reels_rail", (step?.params?.get("zone") as? kotlinx.serialization.json.JsonPrimitive)?.content)
    }

    @Test
    fun reel_like_zone_detected() {
        assert(CommentLikesRoutine.isReelLikeZone(980, 1100, 1080, 2400))
        assertFalse(CommentLikesRoutine.isReelLikeZone(980, 1500, 1080, 2400))
    }

    @Test
    fun after_five_likes_closes_comments() {
        val tracker = SessionTracker().apply {
            phase = "reels_comment_likes"
            commentLikesPhase = CommentLikesRoutine.PHASE_IN_COMMENTS
            commentsSheetOpen = true
            commentLikesThisReel = 5
            commentLikesPerReel = 5
        }
        val step = CommentLikesRoutine.nextStep(
            tracker,
            Screen(app = "com.instagram.android", elements = emptyList()),
            ScreenState(screenType = "comments_sheet"),
            android.util.DisplayMetrics().apply { widthPixels = 1080; heightPixels = 2400 },
        )
        assertEquals("press", step?.action)
    }
}
