package com.gamja.recorder

import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.pm.ServiceInfo
import android.media.AudioDeviceInfo
import android.media.AudioManager
import android.media.MediaRecorder
import android.os.Build
import android.os.IBinder
import android.util.Log
import androidx.core.app.NotificationCompat
import androidx.core.app.ServiceCompat
import androidx.core.content.ContextCompat
import java.io.File
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale

/** 화면이 꺼지거나 다른 앱으로 가도 녹음이 끊기지 않도록 포그라운드 서비스에서 녹음한다. */
class RecordingService : Service() {

    companion object {
        private const val TAG = "RecordingService"
        private const val ACTION_START = "start"
        private const val ACTION_STOP = "stop"
        private const val CHANNEL_ID = "recording"
        private const val NOTIFICATION_ID = 1

        fun start(context: Context) {
            ContextCompat.startForegroundService(
                context, Intent(context, RecordingService::class.java).setAction(ACTION_START)
            )
        }

        fun stop(context: Context) {
            context.startService(Intent(context, RecordingService::class.java).setAction(ACTION_STOP))
        }
    }

    private var recorder: MediaRecorder? = null
    private var file: File? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_START -> startRecording()
            ACTION_STOP -> stopRecording()
        }
        return START_NOT_STICKY
    }

    private fun startRecording() {
        if (recorder != null) return
        ServiceCompat.startForeground(
            this, NOTIFICATION_ID, buildNotification(),
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R)
                ServiceInfo.FOREGROUND_SERVICE_TYPE_MICROPHONE else 0
        )

        val name = "녹음_" + SimpleDateFormat("yyyy-MM-dd_HH-mm-ss", Locale.KOREA).format(Date()) + ".m4a"
        val out = File(Storage.recordingDir(this), name)
        val mic = findExternalMic()
        try {
            val r = if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) MediaRecorder(this)
            else @Suppress("DEPRECATION") MediaRecorder()
            r.setAudioSource(MediaRecorder.AudioSource.MIC)
            r.setOutputFormat(MediaRecorder.OutputFormat.MPEG_4)
            r.setAudioEncoder(MediaRecorder.AudioEncoder.AAC)
            r.setAudioSamplingRate(44_100)
            r.setAudioEncodingBitRate(128_000)
            r.setAudioChannels(1)
            r.setOutputFile(out.absolutePath)
            if (mic != null && Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                r.setPreferredDevice(mic)
            }
            r.prepare()
            r.start()
            recorder = r
            file = out
            RecorderState.started(System.currentTimeMillis(), mic?.productName?.toString() ?: "태블릿 내장 마이크")
        } catch (e: Exception) {
            Log.e(TAG, "start failed", e)
            out.delete()
            RecorderState.failed("녹음을 시작하지 못했어요. 다시 눌러 주세요.")
            stopForegroundAndSelf()
        }
    }

    private fun stopRecording() {
        val r = recorder ?: run { stopForegroundAndSelf(); return }
        val out = file
        recorder = null
        file = null
        try {
            r.stop()
            out?.renameTo(File(Storage.pendingDir(this), out.name))
        } catch (e: RuntimeException) {
            // 너무 짧게 녹음하면 stop() 이 실패한다 → 빈 파일은 버린다
            Log.w(TAG, "stop failed", e)
            out?.delete()
        } finally {
            r.release()
        }
        RecorderState.stopped()
        UploadState.refresh(this)
        UploadWorker.enqueue(this)
        stopForegroundAndSelf()
    }

    override fun onDestroy() {
        if (recorder != null) stopRecording()
        super.onDestroy()
    }

    private fun stopForegroundAndSelf() {
        ServiceCompat.stopForeground(this, ServiceCompat.STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    /** USB/유선으로 연결된 외부 마이크가 있으면 그것을 우선 사용한다. */
    private fun findExternalMic(): AudioDeviceInfo? {
        val am = getSystemService(AudioManager::class.java)
        val preferred = listOf(
            AudioDeviceInfo.TYPE_USB_DEVICE,
            AudioDeviceInfo.TYPE_USB_HEADSET,
            AudioDeviceInfo.TYPE_WIRED_HEADSET,
        )
        val inputs = am.getDevices(AudioManager.GET_DEVICES_INPUTS)
        return preferred.firstNotNullOfOrNull { type -> inputs.firstOrNull { it.type == type } }
    }

    private fun buildNotification(): Notification {
        val nm = getSystemService(NotificationManager::class.java)
        nm.createNotificationChannel(
            NotificationChannel(CHANNEL_ID, "녹음", NotificationManager.IMPORTANCE_LOW)
        )
        val open = PendingIntent.getActivity(
            this, 0, Intent(this, MainActivity::class.java),
            PendingIntent.FLAG_IMMUTABLE or PendingIntent.FLAG_UPDATE_CURRENT
        )
        return NotificationCompat.Builder(this, CHANNEL_ID)
            .setSmallIcon(android.R.drawable.ic_btn_speak_now)
            .setContentTitle("녹음 중입니다")
            .setContentText("눌러서 녹음기 화면으로 돌아가기")
            .setContentIntent(open)
            .setOngoing(true)
            .build()
    }
}
