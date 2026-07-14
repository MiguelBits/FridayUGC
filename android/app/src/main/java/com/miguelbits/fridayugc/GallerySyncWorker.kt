package com.miguelbits.fridayugc

import android.content.ContentValues
import android.content.Context
import android.net.Uri
import android.os.Environment
import android.provider.MediaStore
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.OkHttpClient
import okhttp3.Request
import java.util.concurrent.TimeUnit

/** Download due gallery assets from brain into MediaStore. */
class GallerySyncWorker(
    context: Context,
    params: WorkerParameters,
) : CoroutineWorker(context, params) {

    private val http = OkHttpClient.Builder()
        .connectTimeout(20, TimeUnit.SECONDS)
        .readTimeout(120, TimeUnit.SECONDS)
        .build()

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        val brain = BrainClient()
        val sync = runCatching { brain.gallerySync() }.getOrNull() ?: return@withContext Result.retry()
        val prefs = applicationContext.getSharedPreferences("friday_gallery", Context.MODE_PRIVATE)
        val editor = prefs.edit()
        for (item in sync.dueItems) {
            for (asset in item.assets) {
                val uri = downloadToMediaStore(asset.assetId, asset.url)
                if (uri != null) editor.putString("asset:${asset.assetId}", uri.toString())
            }
        }
        editor.apply()
        Result.success()
    }

    private fun downloadToMediaStore(assetId: String, url: String): Uri? {
        val request = Request.Builder().url(url).get().build()
        val bytes = http.newCall(request).execute().use { resp ->
            if (!resp.isSuccessful) return null
            resp.body?.bytes()
        } ?: return null
        val values = ContentValues().apply {
            put(MediaStore.MediaColumns.DISPLAY_NAME, "$assetId.mp4")
            put(MediaStore.MediaColumns.MIME_TYPE, "video/mp4")
            put(MediaStore.MediaColumns.RELATIVE_PATH, Environment.DIRECTORY_MOVIES + "/FridayUGC")
        }
        val resolver = applicationContext.contentResolver
        val uri = resolver.insert(MediaStore.Video.Media.EXTERNAL_CONTENT_URI, values) ?: return null
        resolver.openOutputStream(uri)?.use { it.write(bytes) }
        return uri
    }

    companion object {
        const val WORK_NAME = "friday_gallery_sync"
    }
}
