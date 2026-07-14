package com.miguelbits.fridayugc

import android.accessibilityservice.AccessibilityService
import android.view.accessibility.AccessibilityEvent

/**
 * The single always-on accessibility service. It doesn't run the loop itself; it
 * exposes screen-reading + gesture execution to AgentController via a static handle.
 */
class FridayAccessibilityService : AccessibilityService() {

    lateinit var executor: ActionExecutor
        private set

    @Volatile
    private var lastActivityClass: String = ""

    override fun onServiceConnected() {
        super.onServiceConnected()
        executor = ActionExecutor(this)
        instance = this
    }

    override fun onAccessibilityEvent(event: AccessibilityEvent?) {
        if (event == null) return
        if (event.eventType == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED ||
            event.eventType == AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED
        ) {
            val cls = event.className?.toString().orEmpty()
            if (cls.isNotBlank() && !cls.startsWith("android.")) {
                lastActivityClass = cls
            }
        }
    }

    override fun onInterrupt() {}

    override fun onDestroy() {
        if (instance === this) instance = null
        super.onDestroy()
    }

    fun currentPackage(): String = rootInActiveWindow?.packageName?.toString().orEmpty()

    fun currentActivityClass(): String {
        val root = rootInActiveWindow
        val fromRoot = root?.className?.toString().orEmpty()
        return when {
            fromRoot.isNotBlank() && !fromRoot.startsWith("android.") -> fromRoot
            lastActivityClass.isNotBlank() -> lastActivityClass
            else -> ""
        }
    }

    fun readScreen() = ScreenReader.read(
        rootInActiveWindow,
        packageName = currentPackage(),
        activity = currentActivityClass(),
    )

    companion object {
        @Volatile
        var instance: FridayAccessibilityService? = null
            private set

        val isConnected: Boolean get() = instance != null
    }
}
