package com.miguelbits.fridayugc

import com.miguelbits.fridayugc.model.Screen
import com.miguelbits.fridayugc.model.ScreenState

/**
 * Rule-based screen classifier — general shape, Instagram rules for now.
 * Produces structured state the brain can trust instead of inferring from one word in the tree.
 */
object ScreenClassifier {

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

        if (texts.any { it.contains("add a comment") || it.contains("reply") && it.contains("comment") }) {
            signals.add("comment composer visible")
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

        if (texts.any { it.contains("for you") || it.contains("following") }) {
            signals.add("home feed tabs visible")
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

        val bigScrollable = screen.elements.any { it.scrollable && it.h > 400 && it.w > 200 }
        if (bigScrollable && screen.elements.size < 15) {
            signals.add("sparse tree + large scrollable = reel viewer heuristic")
            return ScreenState(
                appPackage = screen.app,
                activityClass = activityClass,
                screenType = "reels_viewer",
                selectedTab = "reels",
                confidence = 0.72f,
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
