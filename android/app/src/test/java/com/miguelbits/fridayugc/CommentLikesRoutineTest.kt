package com.miguelbits.fridayugc

import com.miguelbits.fridayugc.model.Screen
import com.miguelbits.fridayugc.model.ScreenElement
import com.miguelbits.fridayugc.model.ScreenState
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class CommentLikesRoutineTest {

    @Test
    fun open_comments_always_vision_intent() {
        val tracker = SessionTracker().apply {
            phase = "reels_comment_likes"
            reelsTabOpened = true
        }
        val step = CommentLikesRoutine.nextStep(
            tracker,
            Screen(app = "com.instagram.android", elements = emptyList()),
            ScreenState(screenType = "reels_viewer"),
            android.util.DisplayMetrics().apply { widthPixels = 1080; heightPixels = 2400 },
        )
        assertEquals("intent", step?.action)
        assertEquals("open_comments", (step?.params?.get("name") as? kotlinx.serialization.json.JsonPrimitive)?.content)
        assertTrue(step?.needsScreenshot == true)
    }

    @Test
    fun in_comments_vision_engage_intent() {
        val tracker = SessionTracker().apply {
            phase = "reels_comment_likes"
            commentsSheetOpen = true
            commentLikesPhase = CommentLikesRoutine.PHASE_IN_COMMENTS
        }
        val step = CommentLikesRoutine.nextStep(
            tracker,
            Screen(app = "com.instagram.android", elements = emptyList()),
            ScreenState(screenType = "comments_sheet"),
            android.util.DisplayMetrics().apply { widthPixels = 1080; heightPixels = 2400 },
        )
        assertEquals("intent", step?.action)
        assertEquals("engage_comments", (step?.params?.get("name") as? kotlinx.serialization.json.JsonPrimitive)?.content)
        assertTrue(step?.needsScreenshot == true)
    }

    @Test
    fun in_comments_scrolls_after_one_like() {
        val tracker = SessionTracker().apply {
            phase = "reels_comment_likes"
            commentsSheetOpen = true
            commentLikesPhase = CommentLikesRoutine.PHASE_IN_COMMENTS
            commentLikesSinceScroll = 2
            commentLikesThisReel = 1
            commentLikesPerReel = 3
        }
        val step = CommentLikesRoutine.nextStep(
            tracker,
            Screen(app = "com.instagram.android", elements = emptyList()),
            ScreenState(screenType = "comments_sheet"),
            android.util.DisplayMetrics().apply { widthPixels = 1080; heightPixels = 2400 },
        )
        assertEquals("scroll", step?.action)
        assertEquals("comments_sheet", (step?.params?.get("zone") as? kotlinx.serialization.json.JsonPrimitive)?.content)
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
    fun comment_heart_verified_when_sheet_before_tap() {
        val before = Screen(
            app = "com.instagram.android",
            elements = listOf(
                ScreenElement(id = 0, text = "Add a comment"),
                ScreenElement(id = 1, text = "Reply"),
            ),
        )
        val after = Screen(
            app = "com.instagram.android",
            elements = listOf(
                ScreenElement(id = 0, text = "Add a comment"),
                ScreenElement(id = 1, text = "Reply"),
            ),
        )
        val beforeFp = ScreenValidator.fingerprint(before)
        val afterFp = ScreenValidator.fingerprint(after)
        val result = OutcomeVerifier.verify(
            "like_comment",
            true,
            before,
            after,
            beforeFp,
            afterFp,
            mapOf("ui_key" to kotlinx.serialization.json.JsonPrimitive("comment_heart")),
            "clips",
        )
        assertEquals("verified", result.status)
    }

    @Test
    fun after_three_likes_closes_comments() {
        val tracker = SessionTracker().apply {
            phase = "reels_comment_likes"
            commentLikesPhase = CommentLikesRoutine.PHASE_IN_COMMENTS
            commentsSheetOpen = true
            commentLikesThisReel = 3
            commentLikesPerReel = 3
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
