package com.miguelbits.fridayugc

import com.miguelbits.fridayugc.model.SessionBudget
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonPrimitive

/** Tracks per-session UGC engagement budgets (mirrors brain SessionBudget). */
class SessionTracker {
    var likesUsed = 0
    var likesMax = 25
    var storyLikesUsed = 0
    var storyLikesMax = 12
    var reelsScrolled = 0
    var reelsMax = 35
    var commentsUsed = 0
    var commentsMax = 8
    var commentLikesUsed = 0
    var commentLikesMax = 50
    var commentLikesThisReel = 0
    var commentLikesPerReel = 5
    var dmsUsed = 0
    var dmsMax = 10
    var followsUsed = 0
    var followsMax = 3
    var savesUsed = 0
    var savesMax = 5
    var phase: String = "reels"
    var reelsTabOpened = false
    var reelsSwipeAttempted = false
    var commentsSheetOpen = false
    var commentLikesPhase: String = CommentLikesRoutine.PHASE_ON_REELS
    var readyForNextReel = false
    var commentLikesSinceScroll = 0
    var commentSheetScrolls = 0

    fun applyFromBudget(budget: SessionBudget) {
        likesMax = budget.likesMax
        storyLikesMax = budget.storyLikesMax
        reelsMax = budget.reelsMax
        commentsMax = budget.commentsMax
        commentLikesMax = budget.commentLikesMax
        commentLikesPerReel = budget.commentLikesPerReel
        dmsMax = budget.dmsMax
        followsMax = budget.followsMax
        savesMax = budget.savesMax
        phase = budget.phase
    }

    fun applyContext(ctx: Map<String, JsonElement>) {
        fun intOf(key: String, fallback: Int) =
            (ctx[key] as? JsonPrimitive)?.content?.toIntOrNull() ?: fallback
        likesUsed = intOf("likes_used", likesUsed)
        likesMax = intOf("likes_max", likesMax)
        storyLikesUsed = intOf("story_likes_used", storyLikesUsed)
        storyLikesMax = intOf("story_likes_max", storyLikesMax)
        reelsScrolled = intOf("reels_scrolled", reelsScrolled)
        reelsMax = intOf("reels_max", reelsMax)
        commentsUsed = intOf("comments_used", commentsUsed)
        commentsMax = intOf("comments_max", commentsMax)
        commentLikesUsed = intOf("comment_likes_used", commentLikesUsed)
        commentLikesMax = intOf("comment_likes_max", commentLikesMax)
        commentLikesThisReel = intOf("comment_likes_this_reel", commentLikesThisReel)
        commentLikesPerReel = intOf("comment_likes_per_reel", commentLikesPerReel)
        dmsUsed = intOf("dms_used", dmsUsed)
        dmsMax = intOf("dms_max", dmsMax)
        followsUsed = intOf("follows_used", followsUsed)
        followsMax = intOf("follows_max", followsMax)
        savesUsed = intOf("saves_used", savesUsed)
        savesMax = intOf("saves_max", savesMax)
        phase = (ctx["phase"] as? JsonPrimitive)?.content ?: phase
        reelsTabOpened = intOf("reels_tab_opened", if (reelsTabOpened) 1 else 0) == 1
        reelsSwipeAttempted = intOf("reels_swipe_attempted", if (reelsSwipeAttempted) 1 else 0) == 1
        commentsSheetOpen = intOf("comments_sheet_open", if (commentsSheetOpen) 1 else 0) == 1
        commentLikesPhase = (ctx["comment_likes_phase"] as? JsonPrimitive)?.content ?: commentLikesPhase
        readyForNextReel = intOf("ready_for_next_reel", if (readyForNextReel) 1 else 0) == 1
        commentLikesSinceScroll = intOf("comment_likes_since_scroll", commentLikesSinceScroll)
        commentSheetScrolls = intOf("comment_sheet_scrolls", commentSheetScrolls)
    }

    fun toContext(): Map<String, JsonElement> = mapOf(
        "likes_used" to JsonPrimitive(likesUsed),
        "likes_max" to JsonPrimitive(likesMax),
        "story_likes_used" to JsonPrimitive(storyLikesUsed),
        "story_likes_max" to JsonPrimitive(storyLikesMax),
        "reels_scrolled" to JsonPrimitive(reelsScrolled),
        "reels_max" to JsonPrimitive(reelsMax),
        "comments_used" to JsonPrimitive(commentsUsed),
        "comments_max" to JsonPrimitive(commentsMax),
        "comment_likes_used" to JsonPrimitive(commentLikesUsed),
        "comment_likes_max" to JsonPrimitive(commentLikesMax),
        "comment_likes_this_reel" to JsonPrimitive(commentLikesThisReel),
        "comment_likes_per_reel" to JsonPrimitive(commentLikesPerReel),
        "dms_used" to JsonPrimitive(dmsUsed),
        "dms_max" to JsonPrimitive(dmsMax),
        "follows_used" to JsonPrimitive(followsUsed),
        "follows_max" to JsonPrimitive(followsMax),
        "saves_used" to JsonPrimitive(savesUsed),
        "saves_max" to JsonPrimitive(savesMax),
        "phase" to JsonPrimitive(phase),
        "reels_tab_opened" to JsonPrimitive(if (reelsTabOpened) 1 else 0),
        "reels_swipe_attempted" to JsonPrimitive(if (reelsSwipeAttempted) 1 else 0),
        "comments_sheet_open" to JsonPrimitive(if (commentsSheetOpen) 1 else 0),
        "comment_likes_phase" to JsonPrimitive(commentLikesPhase),
        "ready_for_next_reel" to JsonPrimitive(if (readyForNextReel) 1 else 0),
        "comment_likes_since_scroll" to JsonPrimitive(commentLikesSinceScroll),
        "comment_sheet_scrolls" to JsonPrimitive(commentSheetScrolls),
    )

    fun record(action: String, params: Map<String, JsonElement> = emptyMap()) {
        when (action) {
            "like" -> if (phase == "reels_comment_likes") commentLikesUsed++ else likesUsed++
            "like_comment" -> {
                commentLikesUsed++
                commentLikesThisReel++
                if (phase == "reels_comment_likes") commentLikesSinceScroll++
            }
            "like_story" -> storyLikesUsed++
            "comment" -> commentsUsed++
            "dm" -> dmsUsed++
            "follow", "unfollow" -> followsUsed++
            "save" -> savesUsed++
            "navigate" -> {
                // reelsTabOpened is set in AgentController after surface verification.
            }
            "tap" -> {
                // Phase transitions for comment-likes are verified in AgentController after tap.
            }
            "press" -> {
                val key = (params["key"] as? JsonPrimitive)?.content?.lowercase()
                if (key == "back" && phase == "reels_comment_likes") {
                    CommentLikesRoutine.onActionCompleted(this, "press", ok = true, params)
                } else if (key == "back") {
                    commentLikesThisReel = 0
                    commentLikesSinceScroll = 0
                    commentSheetScrolls = 0
                    commentsSheetOpen = false
                }
            }
            "scroll" -> {
                val zone = (params["zone"] as? JsonPrimitive)?.content?.lowercase()
                if (phase == "reels_comment_likes" && zone == "comments_sheet") {
                    CommentLikesRoutine.onActionCompleted(this, "scroll", ok = true, params)
                }
            }
            "swipe" -> {
                val dir = (params["direction"] as? JsonPrimitive)?.content?.lowercase()
                val zone = (params["zone"] as? JsonPrimitive)?.content?.lowercase()
                if (dir == "left" && phase == "reels_comment_likes") {
                    // reelsTabOpened is set in AgentController after surface verification.
                }
                if (phase == "reels_comment_likes" && zone == "reels_rail") {
                    reelsScrolled++
                    CommentLikesRoutine.onActionCompleted(this, "swipe", ok = true, params)
                } else if (phase == "reels_comment_likes") {
                    // ignore non-rail swipes while in comment-likes (e.g. accidental)
                } else {
                    reelsScrolled++
                    commentLikesThisReel = 0
                    commentLikesSinceScroll = 0
                    commentSheetScrolls = 0
                }
            }
        }
    }
}
