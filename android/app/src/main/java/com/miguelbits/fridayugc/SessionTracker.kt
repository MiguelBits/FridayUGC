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
    )

    fun record(action: String, params: Map<String, JsonElement> = emptyMap()) {
        when (action) {
            "like" -> if (phase == "reels_comment_likes") commentLikesUsed++ else likesUsed++
            "like_comment" -> {
                commentLikesUsed++
                commentLikesThisReel++
            }
            "like_story" -> storyLikesUsed++
            "swipe" -> {
                reelsScrolled++
                commentLikesThisReel = 0
            }
            "comment" -> commentsUsed++
            "dm" -> dmsUsed++
            "follow", "unfollow" -> followsUsed++
            "save" -> savesUsed++
            "press" -> {
                val key = (params["key"] as? JsonPrimitive)?.content?.lowercase()
                if (key == "back") commentLikesThisReel = 0
            }
        }
    }
}
