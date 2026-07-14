package com.miguelbits.fridayugc

import android.inputmethodservice.InputMethodService
import android.view.View
import android.view.inputmethod.EditorInfo
import android.view.inputmethod.InputConnection

/**
 * Minimal agent IME — commits text into the focused field when accessibility SET_TEXT fails.
 * Enable in Settings → System → Languages → On-screen keyboard → Friday Agent IME.
 */
class FridayInputMethodService : InputMethodService() {

    override fun onCreate() {
        super.onCreate()
        instance = this
    }

    override fun onDestroy() {
        if (instance === this) instance = null
        super.onDestroy()
    }

    override fun onCreateInputView(): View =
        layoutInflater.inflate(R.layout.friday_ime_panel, null)

    override fun onStartInput(attribute: EditorInfo?, restarting: Boolean) {
        super.onStartInput(attribute, restarting)
        instance = this
    }

    companion object {
        @Volatile
        private var instance: FridayInputMethodService? = null

        fun commitText(text: String): Boolean {
            val ic: InputConnection = instance?.currentInputConnection ?: return false
            ic.beginBatchEdit()
            val ok = ic.commitText(text, 1)
            ic.endBatchEdit()
            return ok
        }
    }
}
