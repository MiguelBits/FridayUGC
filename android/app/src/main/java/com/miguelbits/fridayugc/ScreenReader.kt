package com.miguelbits.fridayugc

import android.graphics.Rect
import android.view.accessibility.AccessibilityNodeInfo
import com.miguelbits.fridayugc.model.Screen
import com.miguelbits.fridayugc.model.ScreenElement

/**
 * Flattens the live accessibility tree into a compact, indexed element list the
 * brain can reason over. Index == position in the returned list; ActionExecutor
 * resolves an index back to a node by re-walking the tree the same way.
 */
object ScreenReader {

    private const val MAX_ELEMENTS = 80

    fun read(root: AccessibilityNodeInfo?, packageName: String, activity: String): Screen {
        val elements = ArrayList<ScreenElement>()
        if (root != null) {
            val nodes = ArrayList<AccessibilityNodeInfo>()
            collect(root, nodes)
            nodes.take(MAX_ELEMENTS).forEachIndexed { index, node ->
                val rect = Rect()
                node.getBoundsInScreen(rect)
                elements.add(
                    ScreenElement(
                        id = index,
                        role = simpleRole(node),
                        text = nodeText(node),
                        scrollable = node.isScrollable,
                        editable = node.isEditable,
                        clickable = node.isClickable,
                        x = if (rect.isEmpty) 0 else rect.left,
                        y = if (rect.isEmpty) 0 else rect.top,
                        w = if (rect.isEmpty) 0 else rect.width(),
                        h = if (rect.isEmpty) 0 else rect.height(),
                    )
                )
            }
        }
        return Screen(app = packageName, activity = activity, elements = elements)
    }

    /** Return the node at [index] using the same traversal order as [read]. */
    fun nodeAt(root: AccessibilityNodeInfo?, index: Int): AccessibilityNodeInfo? {
        if (root == null) return null
        val nodes = ArrayList<AccessibilityNodeInfo>()
        collect(root, nodes)
        return nodes.getOrNull(index)
    }

    /** Find first element index whose text/desc/resource id contains any keyword. */
    fun indexByText(root: AccessibilityNodeInfo?, vararg keywords: String): Int? {
        if (root == null) return null
        val nodes = ArrayList<AccessibilityNodeInfo>()
        collect(root, nodes)
        val lower = keywords.map { it.lowercase() }
        nodes.forEachIndexed { index, node ->
            val hay = nodeText(node).lowercase()
            if (lower.any { hay.contains(it) }) return index
        }
        return null
    }

    /**
     * Instagram bottom bar icons often have no text — find by resource id hint or
     * position (home=0, reels=1, create=2, search=3, profile=4).
     */
    fun indexBottomNavTab(root: AccessibilityNodeInfo?, tab: String, screenHeight: Int): Int? {
        if (root == null) return null
        val nodes = ArrayList<AccessibilityNodeInfo>()
        collect(root, nodes)
        val tabLower = tab.lowercase()
        val idHints = when (tabLower) {
            "reels" -> listOf("clips", "reel", "reels_tab", "tab_clips")
            "home" -> listOf("feed_tab", "home_tab", "tab_feed")
            "search" -> listOf("search_tab", "tab_search", "explore")
            "profile" -> listOf("profile_tab", "tab_profile")
            "inbox" -> listOf("direct_tab", "inbox", "messages")
            "create" -> listOf("creation_tab", "camera", "new_post")
            else -> listOf(tabLower)
        }
        nodes.forEachIndexed { index, node ->
            val id = node.viewIdResourceName?.lowercase().orEmpty()
            if (idHints.any { id.contains(it) }) return index
        }
        val barMinY = (screenHeight * 0.82f).toInt()
        val barNodes = nodes.mapIndexedNotNull { index, node ->
            val rect = Rect()
            node.getBoundsInScreen(rect)
            if (!rect.isEmpty && rect.centerY() >= barMinY && node.isClickable) index to rect.centerX()
            else null
        }.sortedBy { it.second }
        if (barNodes.size >= 4) {
            val pos = when (tabLower) {
                "home" -> 0
                "reels" -> 1
                "create" -> 2
                "search" -> minOf(3, barNodes.lastIndex)
                "profile" -> barNodes.lastIndex
                else -> -1
            }
            if (pos >= 0 && pos < barNodes.size) return barNodes[pos].first
        }
        return null
    }

    private fun collect(node: AccessibilityNodeInfo, out: MutableList<AccessibilityNodeInfo>) {
        if (out.size >= MAX_ELEMENTS) return
        val interesting = node.isClickable || node.isScrollable || node.isEditable ||
            !node.text.isNullOrBlank() || !node.contentDescription.isNullOrBlank() ||
            !node.viewIdResourceName.isNullOrBlank()
        if (interesting) out.add(node)
        for (i in 0 until node.childCount) {
            node.getChild(i)?.let { collect(it, out) }
        }
    }

    private fun nodeText(node: AccessibilityNodeInfo): String {
        val parts = mutableListOf<String>()
        node.viewIdResourceName?.substringAfterLast('/')?.takeIf { it.isNotBlank() }?.let {
            parts.add("id:$it")
        }
        val t = node.text?.toString()?.trim().orEmpty()
        if (t.isNotEmpty()) parts.add(t.take(80))
        val desc = node.contentDescription?.toString()?.trim().orEmpty()
        if (desc.isNotEmpty() && desc != t) parts.add(desc.take(80))
        return parts.joinToString(" | ").take(120)
    }

    private fun simpleRole(node: AccessibilityNodeInfo): String {
        val cls = node.className?.toString().orEmpty()
        return when {
            node.isEditable -> "edittext"
            node.isScrollable -> "scrollable"
            cls.endsWith("Button") || node.isClickable -> "button"
            cls.endsWith("ImageView") -> "image"
            cls.endsWith("TextView") -> "text"
            else -> cls.substringAfterLast('.').ifEmpty { "view" }.lowercase()
        }
    }
}
