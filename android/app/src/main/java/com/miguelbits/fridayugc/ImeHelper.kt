package com.miguelbits.fridayugc

import android.accessibilityservice.AccessibilityService
import android.content.Context
import android.content.Intent
import android.os.Bundle
import android.provider.Settings
import android.view.accessibility.AccessibilityNodeInfo
import kotlinx.coroutines.delay

/** Fallback text input via custom IME when ACTION_SET_TEXT fails (MANTIS pattern). */
object ImeHelper {

    fun isFridayImeEnabled(context: Context): Boolean {
        val enabled = Settings.Secure.getString(
            context.contentResolver,
            Settings.Secure.ENABLED_INPUT_METHODS,
        ).orEmpty()
        return enabled.contains("${context.packageName}/.FridayInputMethodService")
    }

    fun openImeSettings(context: Context) {
        context.startActivity(
            Intent(Settings.ACTION_INPUT_METHOD_SETTINGS).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK),
        )
    }

    suspend fun typeIntoNode(
        service: AccessibilityService,
        node: AccessibilityNodeInfo,
        text: String,
    ): Boolean {
        if (text.isEmpty()) return false
        val args = Bundle().apply {
            putCharSequence(AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE, text)
        }
        if (node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)) return true
        if (!node.performAction(AccessibilityNodeInfo.ACTION_FOCUS)) {
            node.performAction(AccessibilityNodeInfo.ACTION_CLICK)
        }
        delay(120)
        if (FridayInputMethodService.commitText(text)) return true
        return node.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, args)
    }
}
