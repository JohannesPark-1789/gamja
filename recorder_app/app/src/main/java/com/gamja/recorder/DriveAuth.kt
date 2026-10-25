package com.gamja.recorder

import android.content.Context
import com.google.android.gms.auth.api.identity.AuthorizationRequest
import com.google.android.gms.auth.api.identity.AuthorizationResult
import com.google.android.gms.auth.api.identity.Identity
import com.google.android.gms.common.api.Scope
import kotlinx.coroutines.tasks.await

object DriveAuth {
    /** 이 앱이 만든 파일/폴더에만 접근하는 최소 권한. */
    private const val DRIVE_FILE_SCOPE = "https://www.googleapis.com/auth/drive.file"

    private val request: AuthorizationRequest =
        AuthorizationRequest.builder()
            .setRequestedScopes(listOf(Scope(DRIVE_FILE_SCOPE)))
            .build()

    /**
     * 권한이 이미 있으면 화면 없이 바로 토큰이 담긴 결과를 돌려준다.
     * 처음이거나 권한이 사라졌다면 result.hasResolution() 이 true 이고,
     * 화면(액티비티)에서 result.pendingIntent 를 띄워야 한다.
     */
    suspend fun authorize(context: Context): AuthorizationResult =
        Identity.getAuthorizationClient(context).authorize(request).await()
}
