package com.miguelbits.fridayugc

import com.miguelbits.fridayugc.model.Screen
import com.miguelbits.fridayugc.model.ScreenState

/**
 * Rule-based screen classifier — general shape, Instagram rules for now.
 * Produces structured state the brain can trust instead of inferring from one word in the tree.
 */
object ScreenClassifier {

    fun hasHomeFeedTabs(screen: Screen): Boolean =
        screen.elements.any {
            val t = it.text.lowercase()
            t.contains("for you") || t.contains("following")
        }

    fun classify(screen: Screen, activityClass: String = ""): ScreenState {
        val pkg = screen.app.lowercase()
        val texts = screen.elements.map { it.text.lowercase() }
        val signals = mutableListOf<String>()

        if (pkg.isBlank() || !pkg.contains("instagram")) {
            return ScreenState(
                appPackage = screen.app,
                activityClass = activityClass,
                screenType = if (pkg.isBlank()) "unknown" else "other_app",
                selectedTab = "unknown",
                confidence = if (pkg.isBlank()) 0.2f else 0.9f,
                elementCount = screen.elements.size,
                signals = listOf("foreground is not Instagram"),
                needsVision = true,
            )
        }

        val activityLower = activityClass.lowercase()
        if (activityLower.contains("story") && !activityLower.contains("history")) {
            signals.add("activity suggests story viewer")
            return ScreenState(
                appPackage = screen.app,
                activityClass = activityClass,
                screenType = "story_viewer",
                selectedTab = "home",
                confidence = 0.9f,
                elementCount = screen.elements.size,
                signals = signals,
                needsVision = false,
            )
        }

        if (
            texts.any { it.contains("reply to") && it.contains("story") } ||
            texts.any { it.contains("send message") && it.contains("story") }
        ) {
            signals.add("story viewer chrome")
            return ScreenState(
                appPackage = screen.app,
                activityClass = activityClass,
                screenType = "story_viewer",
                selectedTab = "home",
                confidence = 0.88f,
                elementCount = screen.elements.size,
                signals = signals,
                needsVision = false,
            )
        }

        if (isFullCommentsSheet(screen, activityClass)) {
            signals.add("comments sheet open")
            return ScreenState(
                appPackage = screen.app,
                activityClass = activityClass,
                screenType = "comments_sheet",
                selectedTab = inferTab(texts, signals),
                confidence = 0.88f,
                elementCount = screen.elements.size,
                signals = signals,
                needsVision = false,
            )
        }

        if (activityLower.contains("clips") || activityLower.contains("reel")) {
            signals.add("activity suggests reels")
            return ScreenState(
                appPackage = screen.app,
                activityClass = activityClass,
                screenType = "reels_viewer",
                selectedTab = "reels",
                confidence = 0.92f,
                elementCount = screen.elements.size,
                signals = signals,
                needsVision = screen.elements.size < 8,
            )
        }

        if (texts.any { it.contains("message") || it.contains("inbox") || it.contains("direct") }) {
            if (texts.any { it.contains("primary") || it.contains("requests") || it.contains("search messages") }) {
                signals.add("inbox headers")
                return ScreenState(
                    appPackage = screen.app,
                    activityClass = activityClass,
                    screenType = "inbox",
                    selectedTab = "inbox",
                    confidence = 0.85f,
                    elementCount = screen.elements.size,
                    signals = signals,
                    needsVision = false,
                )
            }
        }

        val hasFeedTabs = texts.any { it.contains("for you") || it.contains("following") }
        val reelsNavSelected = texts.any { it.contains("reels") && it.contains("selected") }
        val bigScrollable = screen.elements.any { it.scrollable && it.h > 400 && it.w > 200 }
        val activitySuggestsReels = activityLower.contains("clips") ||
            (activityLower.contains("reel") && !activityLower.contains("profile"))

        if (reelsNavSelected && !hasFeedTabs) {
            signals.add("reels tab selected, no home feed tabs")
            return ScreenState(
                appPackage = screen.app,
                activityClass = activityClass,
                screenType = "reels_viewer",
                selectedTab = "reels",
                confidence = 0.9f,
                elementCount = screen.elements.size,
                signals = signals,
                needsVision = screen.elements.size < 8,
            )
        }

        if (!hasFeedTabs && bigScrollable && screen.elements.size < 22 && activitySuggestsReels) {
            signals.add("reels activity + full-screen scrollable")
            return ScreenState(
                appPackage = screen.app,
                activityClass = activityClass,
                screenType = "reels_viewer",
                selectedTab = "reels",
                confidence = 0.88f,
                elementCount = screen.elements.size,
                signals = signals,
                needsVision = screen.elements.size < 8,
            )
        }

        if (!hasFeedTabs && bigScrollable && screen.elements.size < 22) {
            signals.add("scrollable feed without tab labels — likely home, not reels")
            return ScreenState(
                appPackage = screen.app,
                activityClass = activityClass,
                screenType = "home_feed",
                selectedTab = "home",
                confidence = 0.55f,
                elementCount = screen.elements.size,
                signals = signals,
                needsVision = true,
            )
        }

        if (texts.any { it.contains("for you") || it.contains("following") }) {
            signals.add("home feed tabs visible")
            if (texts.any { it.contains("your story") || it.contains("'s story") || it.contains("story,") }) {
                signals.add("story tray at top — do NOT tap; use navigate tab reels for Reels")
            }
            return ScreenState(
                appPackage = screen.app,
                activityClass = activityClass,
                screenType = "home_feed",
                selectedTab = "home",
                confidence = 0.9f,
                elementCount = screen.elements.size,
                signals = signals,
                needsVision = screen.elements.size < 10,
            )
        }

        if (texts.any { it.contains("reels") && it.contains("selected") }) {
            signals.add("reels tab selected in nav")
            val bigScroll = screen.elements.any { it.scrollable && it.h > 400 && it.w > 200 }
            if (bigScroll && screen.elements.size < 18) {
                signals.add("full-screen scrollable reel surface")
                return ScreenState(
                    appPackage = screen.app,
                    activityClass = activityClass,
                    screenType = "reels_viewer",
                    selectedTab = "reels",
                    confidence = 0.88f,
                    elementCount = screen.elements.size,
                    signals = signals,
                    needsVision = screen.elements.size < 8,
                )
            }
            signals.add("nav shows reels selected but feed-like density — likely still home")
            return ScreenState(
                appPackage = screen.app,
                activityClass = activityClass,
                screenType = "home_feed",
                selectedTab = "home",
                confidence = 0.55f,
                elementCount = screen.elements.size,
                signals = signals,
                needsVision = true,
            )
        }

        val bigScrollable2 = screen.elements.any { it.scrollable && it.h > 400 && it.w > 200 }
        if (bigScrollable2 && screen.elements.size < 15 && activitySuggestsReels) {
            signals.add("reels activity + sparse tree")
            return ScreenState(
                appPackage = screen.app,
                activityClass = activityClass,
                screenType = "reels_viewer",
                selectedTab = "reels",
                confidence = 0.8f,
                elementCount = screen.elements.size,
                signals = signals,
                needsVision = screen.elements.size < 8,
            )
        }

        if (bigScrollable2 && screen.elements.size < 15) {
            signals.add("sparse tree + scrollable — ambiguous feed surface")
            return ScreenState(
                appPackage = screen.app,
                activityClass = activityClass,
                screenType = "home_feed",
                selectedTab = "home",
                confidence = 0.5f,
                elementCount = screen.elements.size,
                signals = signals,
                needsVision = true,
            )
        }

        if (screen.elements.size > 25) {
            signals.add("dense element tree")
            return ScreenState(
                appPackage = screen.app,
                activityClass = activityClass,
                screenType = "home_feed",
                selectedTab = inferTab(texts, signals),
                confidence = 0.6f,
                elementCount = screen.elements.size,
                signals = signals,
                needsVision = true,
            )
        }

        if (texts.any { it.contains("search") || it.contains("explore") }) {
            signals.add("search/explore cues")
            return ScreenState(
                appPackage = screen.app,
                activityClass = activityClass,
                screenType = "search",
                selectedTab = "search",
                confidence = 0.7f,
                elementCount = screen.elements.size,
                signals = signals,
                needsVision = true,
            )
        }

        signals.add("low confidence — sparse or ambiguous tree")
        return ScreenState(
            appPackage = screen.app,
            activityClass = activityClass,
            screenType = "unknown",
            selectedTab = inferTab(texts, signals),
            confidence = 0.35f,
            elementCount = screen.elements.size,
            signals = signals,
            needsVision = true,
        )
    }

    /**
     * Reel overlay shows "Add comment…" at the bottom — that is NOT the full comments sheet.
     * Treating it as the sheet skips opening comments and taps the wrong targets (reel like toggle).
     */
    fun isReelOverlayComposerOnly(screen: Screen, activityClass: String = ""): Boolean {
        val texts = screen.elements.map { it.text.lowercase() }
        val hasComposer = texts.any { it.contains("add comment") || it.contains("add a comment") }
        if (!hasComposer) return false
        val activityLower = activityClass.lowercase()
        val onReels = activityLower.contains("clips") ||
            (activityLower.contains("reel") && !activityLower.contains("profile"))
        if (!onReels) return false
        return !hasCommentsSheetSignals(texts, screen)
    }

    /** Full bottom sheet with comment rows — not just the reel overlay composer bar. */
    fun isFullCommentsSheet(screen: Screen, activityClass: String = ""): Boolean {
        if (isReelOverlayComposerOnly(screen, activityClass)) return false
        val texts = screen.elements.map { it.text.lowercase() }
        return hasCommentsSheetSignals(texts, screen)
    }

    private fun hasCommentsSheetSignals(texts: List<String>, screen: Screen): Boolean {
        if (texts.any { it.contains("reply") }) return true
        if (texts.any { it.contains("view") && it.contains("comment") }) return true
        if (texts.any { it.contains("view all") }) return true
        val hasComposer = texts.any { it.contains("add comment") || it.contains("add a comment") }
        if (hasComposer && screen.elements.size >= 8) return true
        if (texts.any { it.contains("comments") && !it.contains("selected") && screen.elements.size >= 6 }) {
            return true
        }
        return false
    }

    /** Confirmed Reels surface — never infer from sparse scrollables alone (false-positive on home). */
    fun likelyReelsSurface(state: ScreenState, screen: Screen): Boolean {
        if (hasHomeFeedTabs(screen)) return false
        if (state.screenType == "reels_viewer" || state.screenType == "comments_sheet") return true
        val texts = screen.elements.map { it.text.lowercase() }
        val reelsSelected = texts.any { it.contains("reels") && it.contains("selected") }
        val activityLower = state.activityClass.lowercase()
        val activityReels = activityLower.contains("clips") ||
            (activityLower.contains("reel") && !activityLower.contains("profile"))
        return reelsSelected || activityReels
    }

    private fun inferTab(texts: List<String>, signals: MutableList<String>): String {
        if (texts.any { it.contains("reels") && it.contains("selected") }) {
            signals.add("tab hint: reels selected")
            return "reels"
        }
        if (texts.any { it.contains("home") && it.contains("selected") }) return "home"
        if (texts.any { it.contains("profile") && it.contains("selected") }) return "profile"
        if (texts.any { it.contains("search") && it.contains("selected") }) return "search"
        return "unknown"
    }
}
