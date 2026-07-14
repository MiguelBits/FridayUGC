package com.miguelbits.fridayugc

import android.accessibilityservice.AccessibilityService
import android.graphics.Bitmap
import android.hardware.HardwareBuffer
import android.os.Build
import android.os.Handler
import android.os.Looper
import android.util.Base64
import android.view.Display
import java.io.ByteArrayOutputStream
import kotlin.coroutines.resume
import kotlin.coroutines.suspendCoroutine

/** Accessibility screenshot for the brain (eyes) — Android 11+. */
object ScreenCapture {

    suspend fun captureBase64(service: AccessibilityService, maxSide: Int = 768): String? {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) return null
        return suspendCoroutine { cont ->
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
                            if (bmp == null) {
                                cont.resume(null)
                                return
                            }
                            val scaled = scaleDown(bmp, maxSide)
                            if (scaled !== bmp) bmp.recycle()
                            val out = ByteArrayOutputStream()
                            scaled.compress(Bitmap.CompressFormat.JPEG, 72, out)
                            scaled.recycle()
                            cont.resume(Base64.encodeToString(out.toByteArray(), Base64.NO_WRAP))
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
