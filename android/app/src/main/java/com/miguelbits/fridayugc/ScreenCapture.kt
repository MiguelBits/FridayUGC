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