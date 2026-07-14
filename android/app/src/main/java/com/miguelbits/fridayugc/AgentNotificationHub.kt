package com.miguelbits.fridayugc

import android.content.Context
import com.miguelbits.fridayugc.model.AgentProgress

/** Shared notification state — FGS attaches; workers/controllers publish progress. */
object AgentNotificationHub {
    @Volatile
    private var manager: AgentNotificationManager? = null

    fun attach(context: Context) {
        manager = AgentNotificationManager(context.applicationContext)
    }

    fun detach() {
        manager = null
    }

    fun apply(event: AgentProgress) {
        manager?.apply(event)
    }

    fun currentNotification(context: Context): android.app.Notification {
        val m = manager ?: AgentNotificationManager(context.applicationContext).also { manager = it }
        return m.build()
    }
}
