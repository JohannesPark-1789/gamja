package com.gamja.recorder

import android.content.Context
import android.util.Log
import androidx.work.BackoffPolicy
import androidx.work.Constraints
import androidx.work.CoroutineWorker
import androidx.work.ExistingWorkPolicy
import androidx.work.NetworkType
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import androidx.work.WorkerParameters
import com.google.android.gms.auth.GoogleAuthUtil
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.util.concurrent.TimeUnit

/**
 * pending/ 폴더에 있는 녹음 파일을 모두 드라이브에 올린다.
 * 인터넷이 없으면 연결될 때까지 기다렸다가 자동으로 다시 시도한다.
 */
class UploadWorker(context: Context, params: WorkerParameters) : CoroutineWorker(context, params) {

    companion object {
        private const val TAG = "UploadWorker"
        private const val WORK_NAME = "upload"

        fun enqueue(context: Context) {
            val request = OneTimeWorkRequestBuilder<UploadWorker>()
                .setConstraints(
                    Constraints.Builder().setRequiredNetworkType(NetworkType.CONNECTED).build()
                )
                .setBackoffCriteria(BackoffPolicy.EXPONENTIAL, 30, TimeUnit.SECONDS)
                .build()
            // 업로드 중에 새 녹음이 생겨도 끊지 않고 뒤에 이어서 실행
            WorkManager.getInstance(context)
                .enqueueUniqueWork(WORK_NAME, ExistingWorkPolicy.APPEND_OR_REPLACE, request)
        }
    }

    override suspend fun doWork(): Result = withContext(Dispatchers.IO) {
        val files = Storage.pendingFiles(applicationContext)
        if (files.isEmpty()) return@withContext Result.success()

        val auth = try {
            DriveAuth.authorize(applicationContext)
        } catch (e: Exception) {
            Log.w(TAG, "authorize failed", e)
            return@withContext Result.retry()
        }
        val token = auth.accessToken
        if (auth.hasResolution() || token == null) {
            // 보호자가 화면에서 계정을 다시 연결해야 함
            UploadState.setNeedsAuth(true)
            return@withContext Result.retry()
        }
        UploadState.setNeedsAuth(false)

        val uploader = DriveUploader(applicationContext, token)
        for (file in files) {
            try {
                uploader.upload(file)
                file.renameTo(java.io.File(Storage.uploadedDir(applicationContext), file.name))
                UploadState.refresh(applicationContext)
            } catch (e: AuthExpiredException) {
                GoogleAuthUtil.clearToken(applicationContext, token)
                return@withContext Result.retry()
            } catch (e: Exception) {
                Log.w(TAG, "upload failed: ${file.name}", e)
                return@withContext Result.retry()
            }
        }
        Result.success()
    }
}
