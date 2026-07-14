package com.miguelbits.fridayugc

import com.miguelbits.fridayugc.model.StepResponse
import kotlinx.serialization.json.JsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class MotorPolicyTest {

    @Test
    fun blocksSwipeRightAlways() {
        val resp = StepResponse(
            action = "swipe",
            params = mapOf("direction" to JsonPrimitive("right")),
        )
        val clamped = MotorPolicy.clampCommentLikes(resp, reelsTabOpened = true, screenType = "reels_viewer")
        assertEquals("navigate", clamped?.action)
    }

    @Test
    fun blocksHorizontalBeforeReelsConfirmed() {
        val resp = StepResponse(
            action = "scroll",
            params = mapOf("direction" to JsonPrimitive("left")),
        )
        val clamped = MotorPolicy.clampCommentLikes(resp, reelsTabOpened = false, screenType = "home_feed")
        assertEquals("navigate", clamped?.action)
    }

    @Test
    fun allowsTaggedPagerLeftBeforeReels() {
        val resp = MotorPolicy.pagerSwipeLeft()
        val clamped = MotorPolicy.clampCommentLikes(resp, reelsTabOpened = false, screenType = "home_feed")
        assertNull(clamped)
    }

    @Test
    fun storyViewerForcesBack() {
        val resp = StepResponse(action = "swipe", params = mapOf("direction" to JsonPrimitive("up")))
        val clamped = MotorPolicy.clampCommentLikes(resp, reelsTabOpened = false, screenType = "story_viewer")
        assertEquals("press", clamped?.action)
        assertEquals("back", (clamped?.params?.get("key") as JsonPrimitive).content)
    }
}
