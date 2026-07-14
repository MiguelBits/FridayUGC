package com.miguelbits.fridayugc

import android.content.Context
import android.content.Intent
import android.media.MediaPlayer
import android.speech.RecognitionListener
import android.speech.RecognizerIntent
import android.speech.SpeechRecognizer
import android.speech.tts.TextToSpeech
import android.speech.tts.Voice
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import java.util.Locale

/**
 * Friday's voice: OmniVoice TTS from the brain (preferred) with Android TTS fallback.
 */
class VoiceManager(context: Context) : TextToSpeech.OnInitListener {

    private val appContext = context.applicationContext
    private var tts: TextToSpeech? = TextToSpeech(appContext, this)
    private var ready = false
    private var recognizer: SpeechRecognizer? = null
    private var mediaPlayer: MediaPlayer? = null

    override fun onInit(status: Int) {
        if (status != TextToSpeech.SUCCESS) return
        val engine = tts ?: return
        engine.language = Locale.US
        selectFemaleVoice(engine)
        ready = true
    }

    private fun selectFemaleVoice(engine: TextToSpeech) {
        val voices: Set<Voice> = runCatching { engine.voices }.getOrNull() ?: return
        val preferred = voices.firstOrNull { v ->
            val n = v.name.lowercase()
            v.locale.language == "en" &&
                (n.contains("female") || n.contains("#female") || n.endsWith("-f") || n.contains("en-us-x-sfg"))
        } ?: voices.firstOrNull { it.locale.language == "en" }
        preferred?.let { engine.voice = it }
    }

    /** Play high-quality WAV from the brain (OmniVoice). Falls back to system TTS on failure. */
    suspend fun speakFromBrain(brain: BrainClient, text: String, situation: String? = null) {
        val ok = runCatching {
            val wav = brain.speak(text, situation)
            playWav(wav)
        }.isSuccess
        if (!ok) speak(text)
    }

    fun speak(text: String) {
        if (!ready || text.isBlank()) return
        tts?.speak(text, TextToSpeech.QUEUE_ADD, null, System.nanoTime().toString())
    }

    private suspend fun playWav(bytes: ByteArray) = withContext(Dispatchers.IO) {
        val file = File.createTempFile("friday_tts_", ".wav", appContext.cacheDir)
        try {
            file.writeBytes(bytes)
            withContext(Dispatchers.Main) {
                mediaPlayer?.release()
                mediaPlayer = MediaPlayer().apply {
                    setDataSource(file.absolutePath)
                    prepare()
                    start()
                }
            }
            // Wait for playback to finish (rough).
            while (withContext(Dispatchers.Main) { mediaPlayer?.isPlaying == true }) {
                kotlinx.coroutines.delay(100)
            }
        } finally {
            file.delete()
        }
    }

    fun listen(onResult: (String) -> Unit, onError: (String) -> Unit) {
        if (!SpeechRecognizer.isRecognitionAvailable(appContext)) {
            onError("Speech recognition not available on this device.")
            return
        }
        recognizer?.destroy()
        recognizer = SpeechRecognizer.createSpeechRecognizer(appContext).apply {
            setRecognitionListener(object : RecognitionListener {
                override fun onResults(results: android.os.Bundle?) {
                    val text = results
                        ?.getStringArrayList(SpeechRecognizer.RESULTS_RECOGNITION)
                        ?.firstOrNull()
                        ?.trim()
                    if (!text.isNullOrBlank()) onResult(text) else onError("Didn't catch that.")
                }

                override fun onError(error: Int) {
                    onError("Speech error ($error)")
                }

                override fun onReadyForSpeech(params: android.os.Bundle?) {}
                override fun onBeginningOfSpeech() {}
                override fun onRmsChanged(rmsdB: Float) {}
                override fun onBufferReceived(buffer: ByteArray?) {}
                override fun onEndOfSpeech() {}
                override fun onPartialResults(partialResults: android.os.Bundle?) {}
                override fun onEvent(eventType: Int, params: android.os.Bundle?) {}
            })
            startListening(
                Intent(RecognizerIntent.ACTION_RECOGNIZE_SPEECH).apply {
                    putExtra(RecognizerIntent.EXTRA_LANGUAGE_MODEL, RecognizerIntent.LANGUAGE_MODEL_FREE_FORM)
                    putExtra(RecognizerIntent.EXTRA_LANGUAGE, Locale.US.toLanguageTag())
                    putExtra(RecognizerIntent.EXTRA_MAX_RESULTS, 1)
                    putExtra(RecognizerIntent.EXTRA_PROMPT, "Tell Friday your goal")
                },
            )
        }
    }

    fun shutdown() {
        recognizer?.destroy()
        recognizer = null
        mediaPlayer?.release()
        mediaPlayer = null
        tts?.stop()
        tts?.shutdown()
        tts = null
    }
}
