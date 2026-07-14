package com.miguelbits.fridayugc

import android.content.Context

/** Persisted settings: operating mode, last goal, scheduled job id. */
object FridayPreferences {
    private const val PREFS = "friday_prefs"
    private const val KEY_MODE = "mode"
    private const val KEY_LAST_GOAL = "last_goal"
    private const val KEY_SCHEDULED = "scheduled"
    private const val KEY_AUTONOMOUS = "autonomous"
    private const val KEY_DEVICE_ID = "device_id"

    fun readOnly(context: Context): Boolean =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY_MODE, "read_only") != "full"

    fun setReadOnly(context: Context, readOnly: Boolean) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_MODE, if (readOnly) "read_only" else "full")
            .apply()
    }

    fun modeString(context: Context): String =
        if (readOnly(context)) "read_only" else "full"

    fun lastGoal(context: Context): String =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getString(KEY_LAST_GOAL, "") ?: ""

    fun saveGoal(context: Context, goal: String) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putString(KEY_LAST_GOAL, goal)
            .apply()
    }

    fun isScheduled(context: Context): Boolean =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getBoolean(KEY_SCHEDULED, false)

    fun setScheduled(context: Context, scheduled: Boolean) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putBoolean(KEY_SCHEDULED, scheduled)
            .apply()
    }

    fun autonomous(context: Context): Boolean =
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .getBoolean(KEY_AUTONOMOUS, false)

    fun setAutonomous(context: Context, enabled: Boolean) {
        context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit()
            .putBoolean(KEY_AUTONOMOUS, enabled)
            .apply()
    }

    fun deviceId(context: Context): String {
        val prefs = context.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        var id = prefs.getString(KEY_DEVICE_ID, null)
        if (id.isNullOrBlank()) {
            id = java.util.UUID.randomUUID().toString()
            prefs.edit().putString(KEY_DEVICE_ID, id).apply()
        }
        return id
    }
}
