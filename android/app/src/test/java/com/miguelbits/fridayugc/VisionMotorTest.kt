package com.miguelbits.fridayugc

import kotlinx.serialization.json.JsonPrimitive
import org.junit.Assert.assertEquals
import org.junit.Test

class VisionMotorTest {

    @Test
    fun scaleGroundParams_maps_image_space_to_display() {
        val params = mapOf(
            "x" to JsonPrimitive(345),
            "y" to JsonPrimitive(384),
        )
        val scaled = VisionMotor.scaleGroundParams(params, 1080, 2400, 345, 768)
        assertEquals(1080, (scaled["x"] as JsonPrimitive).content.toInt())
        assertEquals(1200, (scaled["y"] as JsonPrimitive).content.toInt())
    }

    @Test
    fun scaleGroundParams_unchanged_when_same_dimensions() {
        val params = mapOf(
            "x" to JsonPrimitive(990),
            "y" to JsonPrimitive(1250),
        )
        val scaled = VisionMotor.scaleGroundParams(params, 1080, 2400, 1080, 2400)
        assertEquals(990, (scaled["x"] as JsonPrimitive).content.toInt())
        assertEquals(1250, (scaled["y"] as JsonPrimitive).content.toInt())
    }
}
