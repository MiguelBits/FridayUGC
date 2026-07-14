package com.miguelbits.fridayugc

import java.util.concurrent.atomic.AtomicBoolean

/** Prevent concurrent agent sessions (single-flight). */
object AgentRunLock {
    private val running = AtomicBoolean(false)

    fun tryAcquire(): Boolean = running.compareAndSet(false, true)

    fun release() {
        running.set(false)
    }

    fun isActive(): Boolean = running.get()
}
