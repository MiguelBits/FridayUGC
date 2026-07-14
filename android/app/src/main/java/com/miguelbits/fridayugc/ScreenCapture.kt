package com.miguelbits.fridayugc

import android.accessibilityservice.AccessibilityService
import android.graphics.Bitmap
import android.hardware.HardwareBuffer
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.util.Base64
import android.view.Display
import com.miguelbits.fridayugc.model.Screen
import com.miguelbits.fridayugc.model.SomMark
import java.io.ByteArrayOutputStream
import kotlin.coroutines.resume
import kotlin.coroutines.suspendCoroutine

/** Accessibility screenshot for the brain (eyes) — Android 11+. */
object ScreenCapture {

    data class SomCapture(
        val screenshotB64: String,
        val somMarks: List<SomMark>,
    )

    suspend fun captureBase64(service: AccessibilityService, maxSide: Int = 768): String? =
        captureForGrounding(service, null, maxSide)?.screenshotB64

    /** Capture screenshot with optional Set-of-Marks overlay for vision grounding. */
    suspend fun captureForGrounding(
        service: AccessibilityService,
        screen: Screen?,
        maxSide: Int = 768,
        useSom: Boolean = true,
    ): SomCapture? {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) return null
        val bitmap = captureBitmap(service) ?: return null
        val dm = service.resources.displayMetrics
        return try {
            val scaled = scaleDown(bitmap, maxSide)
            if (scaled !== bitmap) bitmap.recycle()
            val (toEncode, marks) = if (useSom && screen != null && screen.elements.isNotEmpty()) {
                val annotated = SetOfMarks.annotate(scaled, screen, dm.widthPixels, dm.heightPixels)
                if (annotated.bitmap !== scaled) scaled.recycle()
                annotated.bitmap to annotated.marks
            } else {
                scaled to emptyList()
            }
            val out = ByteArrayOutputStream()
            toEncode.compress(Bitmap.CompressFormat.JPEG, 72, out)
            toEncode.recycle()
            SomCapture(
                screenshotB64 = Base64.encodeToString(out.toByteArray(), Base64.NO_WRAP),
                somMarks = marks,
            )
        } catch (_: Exception) {
            null
        }
    }

    private suspend fun captureBitmap(service: AccessibilityService): Bitmap? =
        suspendCoroutine { cont ->
            val handler = Handler(Looper.getMainLooper())
            service.takeScreenshot(
                Display.DEFAULT_DISPLAY,
                handler::post,
                object : AccessibilityService.TakeScreenshotCallback {
                    override fun onSuccess(result: AccessibilityService.ScreenshotResult) {
                        try {
                            val hw: HardwareBuffer = result.hardwareBuffer
                            val bmp = Bitmap.wrapHardwareBuffer(hw, result.colorSpace)
                                ?.copy(Bitmap.Config.ARGB_8888, false)
                            hw.close()
                            cont.resume(bmp)
                        } catch (_: Exception) {
                            cont.resume(null)
                        }
                    }

                    override fun onFailure(errorCode: Int) {
                        cont.resume(null)
                    }
                },
            )
        }

    private fun scaleDown(src: Bitmap, maxSide: Int): Bitmap {
        val w = src.width
        val h = src.height
        val longest = maxOf(w, h)
        if (longest <= maxSide) return src
        val scale = maxSide.toFloat() / longest
        val nw = (w * scale).toInt().coerceAtLeast(1)
        val nh = (h * scale).toInt().coerceAtLeast(1)
        return Bitmap.createScaledBitmap(src, nw, nh, true)
    }
}
