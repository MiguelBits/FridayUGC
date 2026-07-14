package com.miguelbits.fridayugc

import com.miguelbits.fridayugc.model.EvaluateInboxRequest
import com.miguelbits.fridayugc.model.EvaluateInboxResponse
import com.miguelbits.fridayugc.model.IncomingMessage
import com.miguelbits.fridayugc.model.RecordReplyRequest
import kotlinx.coroutines.delay

/**
 * Polls the brain for inbox decisions and executes approved DM/comment replies.
 * The brain decides who gets an answer today — not every message.
 */
class InboxController(
    private val brain: BrainClient,
    private val voice: VoiceManager,
    private val onSay: (String) -> Unit = {},
    private val onApproval: suspend (String, String, String) -> Boolean = { _, _, _ -> false },
) {
    /** Phone passes scraped messages; brain returns reply/skip/defer per message. */
    suspend fun processInbox(messages: List<IncomingMessage>) {
        if (messages.isEmpty()) {
            onSay("No new messages.")
            return
        }
        val resp: EvaluateInboxResponse = runCatching {
            brain.evaluateInbox(EvaluateInboxRequest(messages = messages, draftIfReply = true))
        }.getOrElse {
            onSay("Inbox evaluate failed: ${it.message}")
            return
        }

        onSay(resp.policySummary)
        var sent = 0
        for (d in resp.decisions) {
            when (d.action) {
                "skip", "defer" -> onSay("@${d.author}: ${d.action} — ${d.reason}")
                "reply" -> {
                    val draft = d.draft ?: continue
                    val approved = if (d.approvalRequired) {
                        onApproval(d.author, d.channel, draft)
                    } else {
                        true
                    }
                    if (!approved) {
                        onSay("Skipped reply to @${d.author} (not approved).")
                        continue
                    }
                    // Agent loop sends the dm/comment action — here we record after you'd execute.
                    onSay("Reply @${d.author}: $draft")
                    voice.speakFromBrain(brain, "Drafted a reply for ${d.author}.")
                    brain.recordReply(
                        RecordReplyRequest(
                            messageId = d.messageId,
                            author = d.author,
                            channel = d.channel,
                            textSent = draft,
                        ),
                    )
                    sent++
                    delay(kotlin.random.Random.nextLong(3000, 8000))
                }
            }
        }
        onSay("Inbox pass done. Sent $sent replies.")
    }
}
