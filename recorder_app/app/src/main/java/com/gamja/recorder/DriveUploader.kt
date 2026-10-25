package com.gamja.recorder

import android.content.Context
import org.json.JSONArray
import org.json.JSONObject
import java.io.File
import java.io.IOException
import java.net.HttpURLConnection
import java.net.URL
import java.net.URLEncoder

class AuthExpiredException : IOException("Google 토큰 만료")

/** Google Drive REST API(v3)를 직접 호출하는 작은 업로더. */
class DriveUploader(private val context: Context, private val token: String) {

    companion object {
        /** 드라이브에 만들어질 폴더 이름. */
        const val FOLDER_NAME = "엄마 녹음"
        private const val FOLDER_MIME = "application/vnd.google-apps.folder"
        private const val AUDIO_MIME = "audio/mp4"
    }

    fun upload(file: File) {
        val folderId = folderId()
        try {
            uploadResumable(file, folderId)
        } catch (e: FolderMissingException) {
            // 폴더가 삭제됐으면 다시 만들어서 한 번 더 시도
            Prefs.setFolderId(context, null)
            uploadResumable(file, folderId())
        }
    }

    private class FolderMissingException : IOException()

    private fun folderId(): String {
        Prefs.folderId(context)?.let { return it }
        val id = findFolder() ?: createFolder()
        Prefs.setFolderId(context, id)
        return id
    }

    private fun findFolder(): String? {
        val q = "name = '${FOLDER_NAME.replace("'", "\\'")}' and mimeType = '$FOLDER_MIME' and trashed = false"
        val url = "https://www.googleapis.com/drive/v3/files?q=" +
            URLEncoder.encode(q, "UTF-8") + "&fields=files(id)&spaces=drive"
        val conn = open(url, "GET")
        val files = JSONObject(readBody(conn)).optJSONArray("files") ?: JSONArray()
        return if (files.length() > 0) files.getJSONObject(0).getString("id") else null
    }

    private fun createFolder(): String {
        val conn = open("https://www.googleapis.com/drive/v3/files?fields=id", "POST")
        conn.setRequestProperty("Content-Type", "application/json; charset=UTF-8")
        val body = JSONObject().put("name", FOLDER_NAME).put("mimeType", FOLDER_MIME)
        conn.outputStream.use { it.write(body.toString().toByteArray()) }
        return JSONObject(readBody(conn)).getString("id")
    }

    /** 긴 녹음도 안전하게 올라가도록 resumable 업로드를 사용한다. */
    private fun uploadResumable(file: File, folderId: String) {
        val init = open("https://www.googleapis.com/upload/drive/v3/files?uploadType=resumable", "POST")
        init.setRequestProperty("Content-Type", "application/json; charset=UTF-8")
        init.setRequestProperty("X-Upload-Content-Type", AUDIO_MIME)
        init.setRequestProperty("X-Upload-Content-Length", file.length().toString())
        val meta = JSONObject()
            .put("name", file.name)
            .put("mimeType", AUDIO_MIME)
            .put("parents", JSONArray().put(folderId))
        init.outputStream.use { it.write(meta.toString().toByteArray()) }
        if (init.responseCode == 404) throw FolderMissingException()
        readBody(init)
        val location = init.getHeaderField("Location")
            ?: throw IOException("업로드 주소를 받지 못함")

        val put = URL(location).openConnection() as HttpURLConnection
        put.requestMethod = "PUT"
        put.doOutput = true
        put.connectTimeout = 30_000
        put.readTimeout = 120_000
        put.setRequestProperty("Content-Type", AUDIO_MIME)
        put.setFixedLengthStreamingMode(file.length())
        file.inputStream().use { input -> put.outputStream.use { input.copyTo(it) } }
        readBody(put)
    }

    private fun open(url: String, method: String): HttpURLConnection =
        (URL(url).openConnection() as HttpURLConnection).apply {
            requestMethod = method
            connectTimeout = 30_000
            readTimeout = 60_000
            setRequestProperty("Authorization", "Bearer $token")
            if (method != "GET") doOutput = true
        }

    private fun readBody(conn: HttpURLConnection): String {
        val code = conn.responseCode
        if (code == 401) throw AuthExpiredException()
        if (code !in 200..299) {
            val err = conn.errorStream?.bufferedReader()?.use { it.readText() }
            throw IOException("Drive API 오류 $code: $err")
        }
        return conn.inputStream.bufferedReader().use { it.readText() }
    }
}
