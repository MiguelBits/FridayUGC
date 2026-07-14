package com.miguelbits.fridayugc

import com.miguelbits.fridayugc.model.AgentProgress
import org.junit.Assert.assertEquals
import org.junit.Test

class AgentNotificationManagerTest {

    @Test
    fun budgetLineFrom_reflectsTrackerCounters() {
        val tracker = SessionTracker().apply {
            likesUsed = 3
            commentLikesUsed = 12
            reelsScrolled = 4
            phase = "reels_comment_likes"
        }
        val event = AgentNotificationManager.budgetLineFrom(tracker)
        assertEquals("3/25", event.likes)
        assertEquals("12/50", event.commentLikes)
        assertEquals("4/35", event.reels)
        assertEquals("reels_comment_likes", event.phase)
    }
}
