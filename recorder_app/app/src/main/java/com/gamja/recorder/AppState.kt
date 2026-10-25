package com.gamja.recorder

import android.content.Context
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import java.io.File

/** 녹음 진행 상태. 서비스가 쓰고 화면이 읽는다. */
object RecorderState {
    /** 녹음 시작 시각(ms). 녹음 중이 아니면 null. */
    private val _startedAt = MutableStateFlow<Long?>(null)
    val startedAt: StateFlow<Long?> = _startedAt.asStateFlow()

    /** 현재 사용 중인 마이크 이름 (보호자 확인용). */
    private val _micName = MutableStateFlow<String?>(null)
    val micName: StateFlow<String?> = _micName.asStateFlow()

    private val _error = MutableStateFlow<String?>(null)
    val error: StateFlow<String?> = _error.asStateFlow()

    fun started(at: Long, mic: String) {
        _error.value = null
        _micName.value = mic
        _startedAt.value = at
    }

    fun stopped() {
        _startedAt.value = null
    }

    fun failed(message: String) {
        _startedAt.value = null
        _error.value = message
    }
}

/** 업로드 상태: 아직 드라이브에 올라가지 않은 파일 수와 계정 연결 여부. */
object UploadState {
    private val _pending = MutableStateFlow(0)
    val pending: StateFlow<Int> = _pending.asStateFlow()

    private val _needsAuth = MutableStateFlow(false)
    val needsAuth: StateFlow<Boolean> = _needsAuth.asStateFlow()

    fun refresh(context: Context) {
        _pending.value = Storage.pendingFiles(context).size
    }

    fun setNeedsAuth(value: Boolean) {
        _needsAuth.value = value
    }
}

/**
 * 파일 위치.
 * recording/ : 지금 녹음 중인 파일
 * pending/   : 녹음이 끝나 업로드를 기다리는 파일
 * uploaded/  : 드라이브 업로드가 끝난 파일 (태블릿에도 사본 보관)
 */
object Storage {
    private fun dir(context: Context, name: String): File =
        File(context.getExternalFilesDir(null) ?: context.filesDir, name).apply { mkdirs() }

    fun recordingDir(context: Context) = dir(context, "recording")
    fun pendingDir(context: Context) = dir(context, "pending")
    fun uploadedDir(context: Context) = dir(context, "uploaded")

    fun pendingFiles(context: Context): List<File> =
        pendingDir(context).listFiles { f -> f.isFile && f.length() > 0 }
            ?.sortedBy { it.name }
            .orEmpty()
}

object Prefs {
    private const val NAME = "settings"
    private const val KEY_FOLDER_ID = "drive_folder_id"

    private fun prefs(context: Context) = context.getSharedPreferences(NAME, Context.MODE_PRIVATE)

    fun folderId(context: Context): String? = prefs(context).getString(KEY_FOLDER_ID, null)

    fun setFolderId(context: Context, id: String?) {
        prefs(context).edit().putString(KEY_FOLDER_ID, id).apply()
    }
}
