package com.miguelbits.fridayugc

import android.graphics.Rect
import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.content.Intent
import android.graphics.Path
import android.net.Uri
import android.os.Bundle
import android.view.accessibility.AccessibilityNodeInfo
import com.miguelbits.fridayugc.model.StepResponse
import com.miguelbits.fridayugc.tools.ToolRegistry
import kotlinx.coroutines.delay
import kotlinx.serialization.json.JsonPrimitive

/** Executes UGC operator actions — binds motor at execution time via a11y + device memory. */
class ActionExecutor(
    private val service: AccessibilityService,
    private var memoryStore: DeviceMemoryStore? = null,
) {

    data class Result(val ok: Boolean, val error: String? = null)

    private val registry = ToolRegistry(this)

    fun attachMemory(store: DeviceMemoryStore) {
        memoryStore = store
    }

    fun registeredTools(): Set<String> = registry.registeredActions

    private fun root(): AccessibilityNodeInfo? = service.rootInActiveWindow

    private fun intParam(resp: StepResponse, key: String): Int? =
        resp.params[key]?.let { (it as? JsonPrimitive)?.content?.toIntOrNull() }

    private fun strParam(resp: StepResponse, key: String): String? =
        resp.params[key]?.let { (it as? JsonPrimitive)?.content }

    suspend fun execute(resp: StepResponse): Result = registry.dispatch(resp)

    suspend fun runTap(resp: StepResponse): Result = tap(resp)
    suspend fun runScroll(resp: StepResponse): Result = scroll(resp)
    suspend fun runSwipe(resp: StepResponse): Result = swipe(resp)
    suspend fun runType(resp: StepResponse): Result = type(resp)
    suspend fun runPress(resp: StepResponse): Result = press(resp)
    suspend fun runOpenApp(resp: StepResponse): Result = openApp(resp)
    suspend fun runNavigate(resp: StepResponse): Result = navigate(resp)
    suspend fun runComment(resp: StepResponse): Result = comment(resp)
    suspend fun runDm(resp: StepResponse): Result = dm(resp)
    suspend fun runPost(resp: StepResponse): Result = post(resp)

    suspend fun runWait(resp: StepResponse): Result {
        delay((intParam(resp, "ms") ?: 1000).toLong().coerceIn(200, 8000))
        return Result(true)
    }

    private suspend fun tap(resp: StepResponse): Result {
        val id = intParam(resp, "target_id")
        if (id != null) {
            val node = ScreenReader.nodeAt(root(), id) ?: return Result(false, "no node $id")
            val screenH = service.resources.displayMetrics.heightPixels
            if (ScreenReader.isInStoryTrayZone(node, screenH)) {
                return Result(false, "tap blocked — target is in story tray (opens Stories)")
            }
            val clickable = node.findClickableAncestor() ?: node
            if (clickable.performAction(AccessibilityNodeInfo.ACTION_CLICK)) return Result(true)
            val rect = Rect()
            clickable.getBoundsInScreen(rect)
            if (!rect.isEmpty) {
                val ok = GestureHelper.tapHuman(
                    service,
                    rect.centerX() + kotlin.random.Random.nextInt(-6, 7),
                    rect.centerY() + kotlin.random.Random.nextInt(-6, 7),
                )
                delay(300)
                return Result(ok, if (ok) null else "gesture tap failed")
            }
            return Result(false, "click failed")
        }
        val x = intParam(resp, "x"); val y = intParam(resp, "y")
        return if (x != null && y != null) {
            val screenH = service.resources.displayMetrics.heightPixels
            val storyMaxY = (screenH * 0.28f).toInt()
            if (y < storyMaxY) {
                return Result(false, "tap blocked — coordinates in story tray zone")
            }
            val ok = GestureHelper.tapHuman(service, x, y)
            delay(200)
            Result(ok, if (ok) null else "gesture tap failed")
        } else Result(false, "tap needs target_id or x,y")
    }

    private suspend fun tapIndex(index: Int): Result =
        tap(StepResponse(action = "tap", params = mapOf("target_id" to JsonPrimitive(index))))

    private suspend fun navigate(resp: StepResponse): Result {
        val tab = strParam(resp, "tab")?.lowercase() ?: return Result(false, "navigate needs tab")
        val r = root()
        val screenH = service.resources.displayMetrics.heightPixels

        val keywords = when (tab) {
            "home" -> arrayOf("home", "feed", "id:feed", "id:home")
            "reels" -> arrayOf("reels", "clips", "vídeos", "videos", "id:clips", "id:reel", "id:reels")
            "search" -> arrayOf("search", "explore", "id:search")
            "profile" -> arrayOf("profile", "id:profile")
            "inbox" -> arrayOf("messages", "inbox", "direct", "id:direct")
            "activity" -> arrayOf("activity", "notifications", "heart")
            "create" -> arrayOf("create", "new post", "camera", "id:creation")
            else -> arrayOf(tab)
        }

        ScreenReader.indexBottomNavTab(r, tab, screenH)?.let { return tapIndex(it) }
        ScreenReader.indexByTextInBottomNav(r, screenH, *keywords)?.let { return tapIndex(it) }
        // Never indexByText for reels — story tray bubbles match "reel"/"story" and open Stories.

        memoryStore?.lookup("nav_$tab")?.let { (x, y) ->
            val ok = GestureHelper.tapHuman(service, x, y)
            delay(1200)
            return Result(ok, if (ok) null else "memory tap failed for nav_$tab")
        }

        if (tab == "reels") {
            // Deep link only — NO pager swipe fallback. Pager swipes fire from the left
            // screen edge and produce erratic horizontal (often RIGHT) motion that
            // conflicts with Android's back gesture and breaks autonomy.
            openReelsViaIntent()?.let { return it }
        }

        return Result(false, "tab not found: $tab (no a11y label, device memory, or deep link)")
    }

    private fun openReelsViaIntent(): Result? {
        val pkg = resolveInstagramPackage() ?: return null
        for (uri in listOf("https://www.instagram.com/reels/", "instagram://reels")) {
            try {
                val intent = Intent(Intent.ACTION_VIEW, Uri.parse(uri)).apply {
                    setPackage(pkg)
                    addFlags(Intent.FLAG_ACTIVITY_NEW_TASK or Intent.FLAG_ACTIVITY_CLEAR_TOP)
                }
                service.startActivity(intent)
                return Result(true)
            } catch (_: Exception) {
                continue
            }
        }
        return null
    }

    private suspend fun comment(resp: StepResponse): Result {
        val text = strParam(resp, "text").orEmpty()
        intParam(resp, "target_id")?.let { tapIndex(it); delay(600) }
        val editIdx = ScreenReader.indexByText(root(), "comment", "add a comment", "write")
        if (editIdx != null) {
            type(StepResponse("type", mapOf(
                "target_id" to JsonPrimitive(editIdx),
                "text" to JsonPrimitive(text),
            )))
        }
        delay(400)
        val sendIdx = ScreenReader.indexByText(root(), "post", "send", "reply")
        return if (sendIdx != null) tapIndex(sendIdx) else Result(false, "send button not found")
    }

    private suspend fun dm(resp: StepResponse): Result {
        val handle = strParam(resp, "handle")?.removePrefix("@").orEmpty()
        val text = strParam(resp, "text").orEmpty()
        if (handle.isNotBlank()) {
            ScreenReader.indexByText(root(), handle)?.let { tapIndex(it); delay(700) }
        }
        val editIdx = ScreenReader.indexByText(root(), "message", "write a message")
            ?: intParam(resp, "target_id")
        if (editIdx == null) return Result(false, "dm field not found")
        type(StepResponse("type", mapOf(
            "target_id" to JsonPrimitive(editIdx),
            "text" to JsonPrimitive(text),
        )))
        delay(400)
        val sendIdx = ScreenReader.indexByText(root(), "send")
        return if (sendIdx != null) tapIndex(sendIdx) else Result(false, "dm send not found")
    }

    private suspend fun post(resp: StepResponse): Result {
        val mediaPath = strParam(resp, "media_path") ?: strParam(resp, "media_uri")
        if (!mediaPath.isNullOrBlank()) {
            val open = openApp(StepResponse(action = "open_app", params = mapOf("package" to JsonPrimitive(mediaPath))))
            if (!open.ok) return open
            delay(1200)
        }
        val caption = strParam(resp, "caption").orEmpty()
        if (caption.isNotBlank()) {
            ScreenReader.indexByText(root(), "caption", "write a caption")?.let { capIdx ->
                type(StepResponse("type", mapOf(
                    "target_id" to JsonPrimitive(capIdx),
                    "text" to JsonPrimitive(caption),
                )))
            }
        }
        delay(500)
        val shareIdx = ScreenReader.indexByText(root(), "share", "post")
        return if (shareIdx != null) tapIndex(shareIdx) else Result(false, "post/share button not found")
    }

    private suspend fun scroll(resp: StepResponse): Result {
        val dir = strParam(resp, "direction")?.lowercase() ?: "down"
        if (dir == "right") {
            return Result(false, "scroll RIGHT blocked on Instagram (Stories risk)")
        }
        if (dir == "left") {
            val ok = GestureHelper.swipeFeedPager(service, dir)
            delay(350)
            return Result(ok, if (ok) null else "horizontal scroll gesture failed")
        }
        val id = intParam(resp, "target_id")
        val node = if (id != null) ScreenReader.nodeAt(root(), id) else root()?.findScrollable()
        val action = when (dir) {
            "up", "left" -> AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD
            else -> AccessibilityNodeInfo.ACTION_SCROLL_FORWARD
        }
        if (node?.performAction(action) == true) return Result(true)
        val ok = GestureHelper.swipeDirection(service, dir)
        return Result(ok, if (ok) null else "scroll gesture failed")
    }

    private suspend fun swipe(resp: StepResponse): Result {
        val dir = strParam(resp, "direction")?.lowercase() ?: "up"
        if (dir == "right") {
            return Result(false, "swipe RIGHT blocked on Instagram (Stories / wrong pager)")
        }
        val zone = strParam(resp, "zone")?.lowercase()
        val reason = resp.reason
        val ok = when {
            zone == "feed_pager" || zone == "reels_rail" || (dir == "up" && reason.contains("next_reel")) ->
                if (dir == "left" || dir == "right" || zone == "feed_pager") {
                    if (dir == "right") return Result(false, "pager swipe RIGHT blocked")
                    GestureHelper.swipeFeedPager(service, dir.ifBlank { "left" })
                } else {
                    GestureHelper.swipeReelsNext(service)
                }
            dir == "left" || dir == "right" -> {
                if (dir == "right") return Result(false, "horizontal swipe RIGHT blocked")
                if (dir == "left" && !reason.contains(MotorPolicy.ENTER_REELS_PAGER) &&
                    !reason.contains("pager_enter_reels") && !reason.contains("enter_reels")
                ) {
                    return Result(false, "untagged swipe LEFT blocked — use navigate or enter_reels_pager")
                }
                GestureHelper.swipeFeedPager(service, dir)
            }
            else ->
                GestureHelper.swipeDirection(service, dir)
        }
        delay(350)
        return Result(ok, if (ok) null else "swipe gesture failed")
    }

    private suspend fun type(resp: StepResponse): Result {
        val id = intParam(resp, "target_id") ?: return Result(false, "type needs target_id")
        val text = strParam(resp, "text").orEmpty()
        val node = ScreenReader.nodeAt(root(), id) ?: return Result(false, "no node $id")
        return if (ImeHelper.typeIntoNode(service, node, text)) Result(true)
        else Result(false, "set_text and IME failed")
    }

    private fun press(resp: StepResponse): Result {
        val key = strParam(resp, "key") ?: "back"
        val global = when (key) {
            "home" -> AccessibilityService.GLOBAL_ACTION_HOME
            "recents" -> AccessibilityService.GLOBAL_ACTION_RECENTS
            else -> AccessibilityService.GLOBAL_ACTION_BACK
        }
        return Result(service.performGlobalAction(global))
    }

    private fun openApp(resp: StepResponse): Result {
        var pkg = strParam(resp, "package") ?: return Result(false, "open_app needs package")
        val lower = pkg.lowercase()
        if (
            lower.contains("google") || lower.contains("chrome") || lower.contains("browser") ||
            lower.contains("instagram.com") || lower.contains("http") || lower.contains("instagram")
        ) {
            val resolved = resolveInstagramPackage()
                ?: return Result(false, "Instagram not found — install it from Play Store first")
            pkg = resolved
        }
        val intent = service.packageManager.getLaunchIntentForPackage(pkg)
            ?: return Result(false, "cannot launch: $pkg (disabled or no launcher)")
        intent.addFlags(
            Intent.FLAG_ACTIVITY_NEW_TASK or
                Intent.FLAG_ACTIVITY_RESET_TASK_IF_NEEDED or
                Intent.FLAG_ACTIVITY_CLEAR_TOP,
        )
        return try {
            service.startActivity(intent)
            Result(true)
        } catch (e: Exception) {
            Result(false, "launch failed: ${e.message}")
        }
    }

    private fun resolveInstagramPackage(): String? {
        val pm = service.packageManager
        val preferred = listOf("com.instagram.android", "com.instagram.lite")
        for (candidate in preferred) {
            if (pm.getLaunchIntentForPackage(candidate) != null) return candidate
        }
        val apps = pm.getInstalledApplications(0)
        for (info in apps) {
            val name = info.packageName
            if (name.contains("instagram", ignoreCase = true) && pm.getLaunchIntentForPackage(name) != null) {
                return name
            }
        }
        return null
    }
}

private fun AccessibilityNodeInfo.findClickableAncestor(): AccessibilityNodeInfo? {
    var n: AccessibilityNodeInfo? = this
    var depth = 0
    while (n != null && depth < 8) {
        if (n.isClickable) return n
        n = n.parent
        depth++
    }
    return this
}

private fun AccessibilityNodeInfo.findScrollable(): AccessibilityNodeInfo? {
    if (isScrollable) return this
    for (i in 0 until childCount) {
        getChild(i)?.findScrollable()?.let { return it }
    }
    return null
}
