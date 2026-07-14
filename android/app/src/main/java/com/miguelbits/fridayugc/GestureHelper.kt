package com.miguelbits.fridayugc

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.graphics.Path
import kotlinx.coroutines.suspendCancellableCoroutine
import kotlin.coroutines.resume

/** Dispatch accessibility gestures and await completion. */
object GestureHelper {

    suspend fun tap(service: AccessibilityService, x: Int, y: Int): Boolean {
        val path = Path().apply { moveTo(x.toFloat(), y.toFloat()) }
        val stroke = GestureDescription.StrokeDescription(path, 0, 60)
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
        val path = Path().apply {
            moveTo(x1, y1)
            lineTo(x2, y2)
        }
        val stroke = GestureDescription.StrokeDescription(path, 0, durationMs)
        return dispatch(service, GestureDescription.Builder().addStroke(stroke).build())
    }

    suspend fun swipeDirection(service: AccessibilityService, dir: String): Boolean {
        val dm = service.resources.displayMetrics
        val cx = dm.widthPixels / 2f
        val cy = dm.heightPixels / 2f
        val d = dm.heightPixels * 0.35f
        return when (dir) {
            "up" -> swipe(service, cx, cy + d, cx, cy - d)
            "down" -> swipe(service, cx, cy - d, cx, cy + d)
            "left" -> swipe(service, cx + d, cy, cx - d, cy)
            else -> swipe(service, cx - d, cy, cx + d, cy)
        }
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
