package com.miguelbits.fridayugc

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.graphics.Path
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume
import kotlin.random.Random

/** Human-like motor synthesis — jitter, curves, variable timing. */
object GestureHelper {

    suspend fun tap(service: AccessibilityService, x: Int, y: Int): Boolean =
        tapHuman(service, x, y)

    suspend fun tapHuman(service: AccessibilityService, x: Int, y: Int): Boolean {
        val jx = x + Random.nextInt(-10, 11)
        val jy = y + Random.nextInt(-10, 11)
        val duration = Random.nextLong(45, 95)
        val path = Path().apply { moveTo(jx.toFloat(), jy.toFloat()) }
        val stroke = GestureDescription.StrokeDescription(path, 0, duration)
        return dispatch(service, GestureDescription.Builder().addStroke(stroke).build())
    }

    /** Tight tap for rail icons — avoids jitter onto audio/share below. */
    suspend fun tapPrecise(service: AccessibilityService, x: Int, y: Int): Boolean {
        val jx = x + Random.nextInt(-3, 4)
        val jy = y + Random.nextInt(-3, 4)
        val path = Path().apply { moveTo(jx.toFloat(), jy.toFloat()) }
        val stroke = GestureDescription.StrokeDescription(path, 0, Random.nextLong(50, 80))
        return dispatch(service, GestureDescription.Builder().addStroke(stroke).build())
    }

    suspend fun swipe(
        service: AccessibilityService,
        x1: Float,
        y1: Float,
        x2: Float,
        y2: Float,
        durationMs: Long = 350,
    ): Boolean {
        val path = humanSwipePath(x1, y1, x2, y2)
        val duration = (durationMs + Random.nextLong(-60, 80)).coerceIn(180, 650)
        val stroke = GestureDescription.StrokeDescription(path, 0, duration)
        return dispatch(service, GestureDescription.Builder().addStroke(stroke).build())
    }

    suspend fun swipeDirection(service: AccessibilityService, dir: String): Boolean {
        val dm = service.resources.displayMetrics
        val cx = dm.widthPixels / 2f + Random.nextInt(-24, 25)
        val cy = dm.heightPixels / 2f + Random.nextInt(-40, 41)
        val d = dm.heightPixels * (0.30f + Random.nextFloat() * 0.12f)
        return when (dir) {
            "up" -> swipe(service, cx, cy + d, cx, cy - d)
            "down" -> swipe(service, cx, cy - d, cx, cy + d)
            "left" -> swipe(service, cx + d, cy, cx - d, cy)
            "right" -> swipe(service, cx - d, cy, cx + d, cy)
            else -> swipe(service, cx - d, cy, cx + d, cy)
        }
    }

    /** Finger swipes up inside the comments sheet to load more comment rows. */
    suspend fun scrollCommentsSheet(service: AccessibilityService): Boolean {
        val dm = service.resources.displayMetrics
        val x = dm.widthPixels * (0.45f + Random.nextFloat() * 0.1f)
        val y1 = dm.heightPixels * (0.78f + Random.nextFloat() * 0.04f)
        val y2 = dm.heightPixels * (0.58f + Random.nextFloat() * 0.04f)
        return swipe(service, x, y1, x, y2, Random.nextLong(280, 420))
    }

    /**
     * Vertical swipe on the Reels right rail — avoids carousel / post media in the center.
     */
    suspend fun swipeReelsNext(service: AccessibilityService): Boolean {
        val dm = service.resources.displayMetrics
        // Swipe through the reel body — never start at 0.68+ (audio disc on the right rail).
        val x = dm.widthPixels * (0.82f + Random.nextFloat() * 0.06f)
        val y1 = dm.heightPixels * (0.52f + Random.nextFloat() * 0.06f)
        val y2 = dm.heightPixels * (0.22f + Random.nextFloat() * 0.06f)
        return swipe(service, x, y1, x, y2, Random.nextLong(320, 480))
    }

    /**
     * Horizontal pager swipe through the **center band** (avoids left-edge back gesture + carousels).
     * Finger moves left → next tab to the right (Home → Reels on Instagram).
     */
    /** Fallback when the a11y tree has no bottom-nav labels (icon-only bar). */
    fun bottomNavCoordinates(service: AccessibilityService, tab: String): Pair<Int, Int>? {
        val dm = service.resources.displayMetrics
        val w = dm.widthPixels
        val h = dm.heightPixels
        val y = (h * 0.935f).toInt()
        val slots = when (tab.lowercase()) {
            "home" -> 0
            "reels" -> 1
            "create" -> 2
            "search" -> 3
            "profile" -> 4
            else -> return null
        }
        val x = (w * (0.10f + slots * 0.20f)).toInt()
        return x to y
    }

    suspend fun tapBottomNavTab(service: AccessibilityService, tab: String): Boolean {
        val (x, y) = bottomNavCoordinates(service, tab) ?: return false
        return tapHuman(service, x, y)
    }

    suspend fun swipeFeedPager(service: AccessibilityService, direction: String): Boolean {
        val dm = service.resources.displayMetrics
        val w = dm.widthPixels.toFloat()
        val y = dm.heightPixels * (0.42f + Random.nextFloat() * 0.14f)
        val duration = Random.nextLong(380, 540)
        val dir = direction.lowercase()
        return when (dir) {
            "left" -> {
                val x1 = w * (0.72f + Random.nextFloat() * 0.08f)
                val x2 = w * (0.22f + Random.nextFloat() * 0.08f)
                swipe(service, x1, y, x2, y, duration)
            }
            "right" -> {
                val x1 = w * (0.22f + Random.nextFloat() * 0.08f)
                val x2 = w * (0.72f + Random.nextFloat() * 0.08f)
                swipe(service, x1, y, x2, y, duration)
            }
            else -> false
        }
    }

    private fun humanSwipePath(x1: Float, y1: Float, x2: Float, y2: Float): Path {
        val path = Path()
        path.moveTo(x1, y1)
        val mx = (x1 + x2) / 2f + Random.nextInt(-18, 19)
        val my = (y1 + y2) / 2f + Random.nextInt(-18, 19)
        path.quadTo(mx, my, x2, y2)
        return path
    }

    private suspend fun dispatch(service: AccessibilityService, gesture: GestureDescription): Boolean =
        suspendCancellableCoroutine { cont ->
            val ok = service.dispatchGesture(
                gesture,
                object : AccessibilityService.GestureResultCallback() {
                    override fun onCompleted(gestureDescription: GestureDescription?) {
                        if (cont.isActive) cont.resume(true)
                    }

                    override fun onCancelled(gestureDescription: GestureDescription?) {
                        if (cont.isActive) cont.resume(false)
                    }
                },
                null,
            )
            if (!ok && cont.isActive) cont.resume(false)
        }
}
