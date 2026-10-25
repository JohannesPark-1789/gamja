package com.gamja.recorder

import android.Manifest
import android.content.pm.PackageManager
import android.os.Build
import android.os.Bundle
import android.os.SystemClock
import android.view.WindowManager
import androidx.activity.ComponentActivity
import androidx.activity.compose.setContent
import androidx.activity.result.IntentSenderRequest
import androidx.activity.result.contract.ActivityResultContracts
import androidx.compose.foundation.background
import androidx.compose.foundation.clickable
import androidx.compose.foundation.interaction.MutableInteractionSource
import androidx.compose.foundation.layout.Arrangement
import androidx.compose.foundation.layout.Box
import androidx.compose.foundation.layout.Column
import androidx.compose.foundation.layout.Spacer
import androidx.compose.foundation.layout.fillMaxSize
import androidx.compose.foundation.layout.height
import androidx.compose.foundation.layout.padding
import androidx.compose.foundation.layout.size
import androidx.compose.foundation.shape.CircleShape
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableLongStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.draw.clip
import androidx.compose.ui.graphics.Color
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.unit.dp
import androidx.compose.ui.unit.sp
import androidx.core.content.ContextCompat
import androidx.lifecycle.compose.collectAsStateWithLifecycle
import androidx.lifecycle.lifecycleScope
import com.google.android.gms.auth.api.identity.Identity
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

class MainActivity : ComponentActivity() {

    private var lastTap = 0L

    private val permissionLauncher =
        registerForActivityResult(ActivityResultContracts.RequestMultiplePermissions()) { }

    private val authLauncher =
        registerForActivityResult(ActivityResultContracts.StartIntentSenderForResult()) { result ->
            try {
                val auth = Identity.getAuthorizationClient(this)
                    .getAuthorizationResultFromIntent(result.data)
                if (auth.accessToken != null) {
                    UploadState.setNeedsAuth(false)
                    UploadWorker.enqueue(this)
                }
            } catch (e: Exception) {
                UploadState.setNeedsAuth(true)
            }
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        requestPermissionsIfNeeded()
        checkDriveAuth(interactive = false)

        setContent {
            MaterialTheme {
                val startedAt by RecorderState.startedAt.collectAsStateWithLifecycle()
                val error by RecorderState.error.collectAsStateWithLifecycle()
                val mic by RecorderState.micName.collectAsStateWithLifecycle()
                val pending by UploadState.pending.collectAsStateWithLifecycle()
                val needsAuth by UploadState.needsAuth.collectAsStateWithLifecycle()

                // 녹음 중에는 화면이 꺼지지 않게
                LaunchedEffect(startedAt) {
                    if (startedAt != null) window.addFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                    else window.clearFlags(WindowManager.LayoutParams.FLAG_KEEP_SCREEN_ON)
                }

                RecorderScreen(
                    startedAt = startedAt,
                    error = error,
                    mic = mic,
                    pending = pending,
                    needsAuth = needsAuth,
                    onToggle = ::onToggle,
                    onConnectDrive = { checkDriveAuth(interactive = true) },
                )
            }
        }
    }

    override fun onResume() {
        super.onResume()
        UploadState.refresh(this)
        if (UploadState.pending.value > 0) UploadWorker.enqueue(this)
    }

    private fun onToggle() {
        // 손이 떨려 두 번 눌리는 것을 막는다
        val now = SystemClock.elapsedRealtime()
        if (now - lastTap < 1500) return
        lastTap = now

        if (RecorderState.startedAt.value != null) {
            RecordingService.stop(this)
            return
        }
        if (ContextCompat.checkSelfPermission(this, Manifest.permission.RECORD_AUDIO)
            != PackageManager.PERMISSION_GRANTED
        ) {
            requestPermissionsIfNeeded()
            return
        }
        RecordingService.start(this)
    }

    private fun requestPermissionsIfNeeded() {
        val perms = buildList {
            add(Manifest.permission.RECORD_AUDIO)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
                add(Manifest.permission.POST_NOTIFICATIONS)
            }
        }.filter {
            ContextCompat.checkSelfPermission(this, it) != PackageManager.PERMISSION_GRANTED
        }
        if (perms.isNotEmpty()) permissionLauncher.launch(perms.toTypedArray())
    }

    /** interactive=true 면 필요할 때 구글 계정 선택/권한 화면을 띄운다. */
    private fun checkDriveAuth(interactive: Boolean) {
        lifecycleScope.launch {
            try {
                val result = DriveAuth.authorize(this@MainActivity)
                val intent = result.pendingIntent
                if (result.hasResolution() && intent != null) {
                    UploadState.setNeedsAuth(true)
                    if (interactive) {
                        authLauncher.launch(IntentSenderRequest.Builder(intent.intentSender).build())
                    }
                } else {
                    UploadState.setNeedsAuth(false)
                }
            } catch (e: Exception) {
                UploadState.setNeedsAuth(true)
            }
        }
    }
}

private val Red = Color(0xFFD32F2F)
private val DarkGray = Color(0xFF424242)
private val Green = Color(0xFF2E7D32)
private val Orange = Color(0xFFE65100)

@Composable
private fun RecorderScreen(
    startedAt: Long?,
    error: String?,
    mic: String?,
    pending: Int,
    needsAuth: Boolean,
    onToggle: () -> Unit,
    onConnectDrive: () -> Unit,
) {
    val recording = startedAt != null

    var now by remember { mutableLongStateOf(System.currentTimeMillis()) }
    LaunchedEffect(recording) {
        while (recording) {
            now = System.currentTimeMillis()
            delay(500)
        }
    }

    Column(
        modifier = Modifier
            .fillMaxSize()
            .background(Color.White)
            .padding(24.dp),
        horizontalAlignment = Alignment.CenterHorizontally,
        verticalArrangement = Arrangement.Center,
    ) {
        Text(
            text = if (recording) "녹음 중  " + formatElapsed(now - startedAt!!)
            else "아래 버튼을 누르면\n녹음이 시작됩니다",
            fontSize = 40.sp,
            lineHeight = 52.sp,
            fontWeight = FontWeight.Bold,
            color = if (recording) Red else Color.Black,
            textAlign = TextAlign.Center,
        )

        Spacer(Modifier.height(40.dp))

        // 화면의 대부분을 차지하는 큰 버튼 하나
        Box(
            modifier = Modifier
                .size(340.dp)
                .clip(CircleShape)
                .background(if (recording) DarkGray else Red)
                .clickable(
                    interactionSource = remember { MutableInteractionSource() },
                    indication = null,
                    onClick = onToggle,
                ),
            contentAlignment = Alignment.Center,
        ) {
            Column(horizontalAlignment = Alignment.CenterHorizontally) {
                if (recording) {
                    Box(
                        Modifier
                            .size(90.dp)
                            .clip(RoundedCornerShape(12.dp))
                            .background(Color.White)
                    )
                } else {
                    Box(
                        Modifier
                            .size(90.dp)
                            .clip(CircleShape)
                            .background(Color.White)
                    )
                }
                Spacer(Modifier.height(20.dp))
                Text(
                    text = if (recording) "멈추기" else "녹음",
                    fontSize = 52.sp,
                    fontWeight = FontWeight.Bold,
                    color = Color.White,
                )
            }
        }

        Spacer(Modifier.height(40.dp))

        val (status, statusColor) = when {
            error != null -> error to Orange
            needsAuth && pending > 0 -> "녹음은 태블릿에 보관 중이에요 (${pending}개)\n드라이브 연결이 필요해요" to Orange
            pending > 0 -> "구글 드라이브에 저장하는 중… (${pending}개)" to Orange
            else -> "✓ 녹음은 모두 구글 드라이브에 저장됐어요" to Green
        }
        Text(
            text = status,
            fontSize = 26.sp,
            lineHeight = 34.sp,
            color = statusColor,
            textAlign = TextAlign.Center,
        )

        if (mic != null) {
            Spacer(Modifier.height(12.dp))
            Text(text = "마이크: $mic", fontSize = 16.sp, color = Color.Gray)
        }

        // 보호자가 처음 한 번 설정하는 버튼 (연결되면 사라짐)
        if (needsAuth && !recording) {
            Spacer(Modifier.height(32.dp))
            Button(onClick = onConnectDrive) {
                Text("구글 드라이브 연결하기 (보호자용)", fontSize = 20.sp)
            }
        }
    }
}

private fun formatElapsed(ms: Long): String {
    val total = (ms / 1000).coerceAtLeast(0)
    val h = total / 3600
    val m = (total % 3600) / 60
    val s = total % 60
    return if (h > 0) "%d:%02d:%02d".format(h, m, s) else "%02d:%02d".format(m, s)
}
