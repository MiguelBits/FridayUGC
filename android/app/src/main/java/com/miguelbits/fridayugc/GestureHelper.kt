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

    /**
     * Vertical swipe on the Reels right rail — avoids carousel / post media in the center.
     */
    suspend fun swipeReelsNext(service: AccessibilityService): Boolean {
        val dm = service.resources.displayMetrics
        val x = dm.widthPixels * (0.90f + Random.nextFloat() * 0.04f)
        val y1 = dm.heightPixels * (0.68f + Random.nextFloat() * 0.06f)
        val y2 = dm.heightPixels * (0.25f + Random.nextFloat() * 0.06f)
        return swipe(service, x, y1, x, y2, Random.nextLong(320, 480))
    }

    /**
     * Horizontal pager swipe along the **left gutter** (avoids carousel post media in center).
     * On Instagram home, swipe left opens the Reels tab — prefer bottom-nav when carousel visible.
     */
    suspend fun swipeFeedPager(service: AccessibilityService, direction: String): Boolean {
        val dm = service.resources.displayMetrics
        val y = dm.heightPixels * (0.45f + Random.nextFloat() * 0.12f)
        val leftGutter = dm.widthPixels * (0.03f + Random.nextFloat() * 0.04f)
        val leftReach = dm.widthPixels * (0.32f + Random.nextFloat() * 0.08f)
        val rightReach = dm.widthPixels * (0.68f + Random.nextFloat() * 0.08f)
        val rightGutter = dm.widthPixels * (0.97f - Random.nextFloat() * 0.04f)
        val duration = Random.nextLong(360, 520)
        return when (direction) {
            "left" -> swipe(service, leftReach, y, leftGutter, y, duration)
            "right" -> swipe(service, rightReach, y, rightGutter, y, duration)
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
