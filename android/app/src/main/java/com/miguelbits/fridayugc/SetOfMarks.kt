package com.miguelbits.fridayugc

import android.graphics.Bitmap
import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Rect
import com.miguelbits.fridayugc.model.Screen
import com.miguelbits.fridayugc.model.SomMark

/**
 * Set-of-Marks (SoM) — numbered overlays on interactive elements for vision grounding.
 * Inspired by Open-AutoGLM-App / MANTIS mobile agent patterns.
 */
object SetOfMarks {

    data class Result(
        val bitmap: Bitmap,
        val marks: List<SomMark>,
    )

    private const val MAX_MARKS = 25

    /** Draw numbered marks on [source] for clickable/editable elements in [screen]. */
    fun annotate(
        source: Bitmap,
        screen: Screen,
        displayWidth: Int,
        displayHeight: Int,
    ): Result {
        val scaleX = source.width.toFloat() / displayWidth.coerceAtLeast(1)
        val scaleY = source.height.toFloat() / displayHeight.coerceAtLeast(1)
        val candidates = screen.elements.filter { el ->
            (el.clickable || el.editable) && el.w > 8 && el.h > 8
        }.take(MAX_MARKS)

        val mutable = source.copy(Bitmap.Config.ARGB_8888, true)
        val canvas = Canvas(mutable)
        val boxPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.STROKE
            strokeWidth = 3f
            color = Color.rgb(255, 87, 34)
        }
        val fillPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            style = Paint.Style.FILL
            color = Color.argb(220, 255, 87, 34)
        }
        val textPaint = Paint(Paint.ANTI_ALIAS_FLAG).apply {
            color = Color.WHITE
            textSize = 28f
            isFakeBoldText = true
        }

        val marks = ArrayList<SomMark>(candidates.size)
        candidates.forEachIndexed { idx, el ->
            val markId = idx + 1
            val left = (el.x * scaleX).toInt()
            val top = (el.y * scaleY).toInt()
            val right = ((el.x + el.w) * scaleX).toInt()
            val bottom = ((el.y + el.h) * scaleY).toInt()
            val rect = Rect(left, top, right, bottom)
            canvas.drawRect(rect, boxPaint)
            val label = markId.toString()
            val tw = textPaint.measureText(label)
            val badge = Rect(left, top.coerceAtLeast(0), (left + tw + 16).toInt(), top + 36)
            canvas.drawRect(badge, fillPaint)
            canvas.drawText(label, left + 8f, top + 26f, textPaint)
            val cx = ((el.x + el.w / 2) * scaleX).toInt()
            val cy = ((el.y + el.h / 2) * scaleY).toInt()
            marks.add(
                SomMark(
                    markId = markId,
                    x = cx,
                    y = cy,
                    text = el.text.take(80),
                    elementId = el.id,
                ),
            )
        }
        return Result(mutable, marks)
    }
}
