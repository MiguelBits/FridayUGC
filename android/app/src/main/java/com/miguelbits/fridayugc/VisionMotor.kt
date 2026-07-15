package com.miguelbits.fridayugc

import com.miguelbits.fridayugc.model.GroundRequest
import com.miguelbits.fridayugc.model.Screen
import com.miguelbits.fridayugc.model.ScreenState
import com.miguelbits.fridayugc.model.StepResponse
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonPrimitive

/**
 * Pure-vision motor: screenshot → brain.ground(anchor) → tap/like params.
 * No accessibility-tree targeting or coordinate fallbacks.
 */
object VisionMotor {

    val REELS_ANCHORS = setOf("nav_reels", "comments_icon", "comment_heart")

    suspend fun groundToStep(
        svc: FridayAccessibilityService,
        brain: BrainClient,
        anchor: String,
        screen: Screen,
        screenState: ScreenState,
        screenshotB64: String? = null,
        rowIndex: Int = 0,
        fallbackAction: String = "tap",
        deviceId: String = "",
        imageWidth: Int = 0,
        imageHeight: Int = 0,
    ): IntentResolver.ResolveResult {
        val shot = screenshotB64?.takeIf { it.isNotBlank() }
            ?: screen.screenshotB64?.takeIf { it.isNotBlank() }
        if (shot == null) {
            return IntentResolver.ResolveResult(
                StepResponse(
                    action = "wait",
                    params = mapOf("ms" to JsonPrimitive(300)),
                    reason = "$anchor needs screenshot",
                ),
                needsScreenshot = true,
                uiKey = anchor,
            )
        }
        val dm = svc.resources.displayMetrics
        return runCatching {
            val ground = brain.ground(
                GroundRequest(
                    anchor = anchor,
                    screenshotB64 = shot,
                    screenWidth = dm.widthPixels,
                    screenHeight = dm.heightPixels,
                    screenType = screenState.screenType,
                    elements = emptyList(),
                    rowIndex = rowIndex,
                    useSom = false,
                    deviceId = deviceId,
                ),
            )
            if (ground.needsScreenshot || ground.params.isEmpty()) {
                IntentResolver.ResolveResult(
                    StepResponse(
                        action = "wait",
                        params = mapOf("ms" to JsonPrimitive(400)),
                        reason = ground.reason.ifBlank { "$anchor ground empty" },
                    ),
                    needsScreenshot = true,
                    uiKey = anchor,
                )
            } else {
                val action = ground.action.ifBlank { fallbackAction }
                val scaled = scaleGroundParams(
                    ground.params,
                    dm.widthPixels,
                    dm.heightPixels,
                    imageWidth,
                    imageHeight,
                )
                val paramsWithKey = scaled + mapOf("ui_key" to JsonPrimitive(anchor))
                IntentResolver.ResolveResult(
                    StepResponse(
                        action = action,
                        params = paramsWithKey,
                        reason = "vision ground: ${ground.reason}",
                    ),
                    uiKey = anchor,
                )
            }
        }.getOrElse {
            IntentResolver.ResolveResult(
                StepResponse(
                    action = "wait",
                    params = mapOf("ms" to JsonPrimitive(500)),
                    reason = "ground failed: ${it.message}",
                ),
                needsScreenshot = true,
                uiKey = anchor,
            )
        }
    }

    /** Fallback rescale when brain returns coords in encoded image space. */
    fun scaleGroundParams(
        params: Map<String, JsonElement>,
        screenW: Int,
        screenH: Int,
        imageW: Int,
        imageH: Int,
    ): Map<String, JsonElement> {
        if (imageW <= 0 || imageH <= 0 || screenW <= 0 || screenH <= 0) return params
        if (imageW == screenW && imageH == screenH) return params
        val x = (params["x"] as? JsonPrimitive)?.content?.toIntOrNull() ?: return params
        val y = (params["y"] as? JsonPrimitive)?.content?.toIntOrNull() ?: return params
        if (x <= imageW && y <= imageH) {
            val sx = screenW.toFloat() / imageW
            val sy = screenH.toFloat() / imageH
            return params + mapOf(
                "x" to JsonPrimitive((x * sx).toInt().coerceIn(0, screenW)),
                "y" to JsonPrimitive((y * sy).toInt().coerceIn(0, screenH)),
            )
        }
        return params
    }
}
