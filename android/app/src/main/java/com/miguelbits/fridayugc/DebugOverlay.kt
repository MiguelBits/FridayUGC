package com.miguelbits.fridayugc

import android.accessibilityservice.AccessibilityService
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.PixelFormat
import android.graphics.Rect
import android.os.Build
import android.view.Gravity
import android.view.View
import android.view.WindowManager
import android.view.accessibility.AccessibilityNodeInfo
import com.miguelbits.fridayugc.model.Screen

/**
 * Dev overlay showing indexed element bounds (AccessibilityServiceWithCompose pattern, View-based).
 */
class DebugOverlay(private val service: AccessibilityService) {

    private val wm = service.getSystemService(WindowManager::class.java)
    private var overlayView: View? = null
    private var lastScreen: Screen? = null

    fun show(screen: Screen) {
        lastScreen = screen
        if (overlayView == null) {
            overlayView = OverlayView(service).also { view ->
                val type = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                    WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY
                } else {
                    @Suppress("DEPRECATION")
                    WindowManager.LayoutParams.TYPE_SYSTEM_OVERLAY
                }
                val params = WindowManager.LayoutParams(
                    WindowManager.LayoutParams.MATCH_PARENT,
                    WindowManager.LayoutParams.MATCH_PARENT,
                    type,
                    WindowManager.LayoutParams.FLAG_NOT_FOCUSABLE or
                        WindowManager.LayoutParams.FLAG_NOT_TOUCHABLE or
                        WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN,
                    PixelFormat.TRANSLUCENT,
                ).apply { gravity = Gravity.TOP or Gravity.START }
                wm.addView(view, params)
            }
        }
        (overlayView as? OverlayView)?.invalidate()
    }

    fun hide() {
        overlayView?.let { wm.removeView(it) }
        overlayView = null
        lastScreen = null
    }

    private inner class OverlayView(context: android.content.Context) : View(context) {
        private val stroke = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.STROKE
            strokeWidth = 2f
            color = Color.GREEN
        }
        private val label = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.WHITE
            textSize = 24f
            setShadowLayer(2f, 0f, 0f, Color.BLACK)
        }

        override fun onDraw(canvas: Canvas) {
            val screen = lastScreen ?: return
            screen.elements.forEach { el ->
                val rect = Rect(el.x, el.y, el.x + el.w, el.y + el.h)
                canvas.drawRect(rect, stroke)
                canvas.drawText(el.id.toString(), rect.left.toFloat(), rect.top + 28f, label)
            }
        }
    }

    companion object {
        fun collectBounds(root: AccessibilityNodeInfo?): Screen =
            ScreenReader.read(root, "", "")
    }
}
