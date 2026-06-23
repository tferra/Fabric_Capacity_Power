#Requires -Version 7.0
<#
.SYNOPSIS
    Enciende (resume) o apaga (suspend) una capacidad de Microsoft Fabric
    usando autenticación por Service Principal (OAuth2 client credentials flow).
#>

Set-StrictMode -Version Latest
$ErrorActionPreference = 'Stop'

# ==============================
# Variables de configuración
# ==============================
$TENANT_ID       = 'TU_TENANT_ID'
$CLIENT_ID       = 'TU_CLIENT_ID'
$CLIENT_SECRET   = 'CAMBIAR_ESTE_VALOR'
$SUBSCRIPTION_ID = 'TU_SUBSCRIPTION_ID'
$RESOURCE_GROUP  = 'TU_RESOURCE_GROUP'
$CAPACITY_NAME   = 'TU_CAPACITY_NAME'



$ACTION = 'suspend'   # 'resume' para encender, 'suspend' para apagar

# ==============================
# Constantes
# ==============================
$ARM_SCOPE            = 'https://management.azure.com/.default'
$API_VERSION          = '2023-11-01'
$POLL_INTERVAL_SEC    = 10
$POLL_TIMEOUT_SEC     = 1800   # 30 minutos


function Get-FabricToken {
    param(
        [string]$TenantId,
        [string]$ClientId,
        [string]$ClientSecret
    )

    Write-Host '[INFO] Autenticando con Azure AD (client credentials)...'

    $tokenUrl = "https://login.microsoftonline.com/$TenantId/oauth2/v2.0/token"
    $body = @{
        client_id     = $ClientId
        client_secret = $ClientSecret
        scope         = $ARM_SCOPE
        grant_type    = 'client_credentials'
    }

    try {
        $response = Invoke-RestMethod -Method Post -Uri $tokenUrl -Body $body -ContentType 'application/x-www-form-urlencoded' -TimeoutSec 30
    }
    catch {
        throw "Error de autenticación: $($_.Exception.Message)"
    }

    if (-not $response.access_token) {
        throw "No se recibió 'access_token' en la respuesta de autenticación."
    }

    Write-Host '[OK] Token obtenido correctamente.'
    return $response.access_token
}


function Get-OperationStatus {
    param([object]$ResponseData)

    if ($null -eq $ResponseData) { return $null }

    if ($ResponseData.status -is [string]) {
        return $ResponseData.status
    }

    if ($ResponseData.properties.provisioningState -is [string]) {
        return $ResponseData.properties.provisioningState
    }

    return $null
}


function Invoke-AsyncPolling {
    param(
        [string]$PollingUrl,
        [hashtable]$Headers
    )

    Write-Host "[INFO] Operación asíncrona detectada. Iniciando polling en: $PollingUrl"

    $start   = [DateTimeOffset]::UtcNow
    $intento = 0

    while ($true) {
        $elapsed = ([DateTimeOffset]::UtcNow - $start).TotalSeconds
        if ($elapsed -gt $POLL_TIMEOUT_SEC) {
            throw "Timeout tras $POLL_TIMEOUT_SEC segundos esperando la operación asíncrona."
        }

        $intento++
        Write-Host "[INFO] Polling intento #$intento..."

        try {
            $resp = Invoke-WebRequest -Method Get -Uri $PollingUrl -Headers $Headers -TimeoutSec 30 -SkipHttpErrorCheck
        }
        catch {
            throw "Error de red durante polling: $($_.Exception.Message)"
        }

        $statusCode = [int]$resp.StatusCode

        if ($statusCode -ge 400) {
            throw "Error HTTP durante polling. HTTP $statusCode. Respuesta: $($resp.Content)"
        }

        $data   = $null
        $estado = $null

        try {
            $data   = $resp.Content | ConvertFrom-Json -ErrorAction Stop
            $estado = Get-OperationStatus -ResponseData $data
        }
        catch { }

        if ($statusCode -eq 202 -and -not $estado) {
            $estado = 'InProgress'
        }

        if (-not $estado) {
            if ($statusCode -eq 200) {
                Write-Host '[OK] Polling finalizado con HTTP 200.'
                return
            }
            Write-Host "[WARN] No se pudo determinar estado en esta iteración; HTTP $statusCode. Se reintenta..."
            Start-Sleep -Seconds $POLL_INTERVAL_SEC
            continue
        }

        Write-Host "[INFO] Estado actual: $estado"

        switch ($estado.Trim().ToLower()) {
            'succeeded' {
                Write-Host '[OK] Operación completada correctamente (Succeeded).'
                return
            }
            'failed' {
                throw "La operación finalizó en Failed. Detalle: $($resp.Content)"
            }
            'canceled' {
                throw 'La operación fue cancelada (Canceled).'
            }
            default {
                Write-Host "[INFO] Esperando $POLL_INTERVAL_SEC segundos antes del siguiente polling..."
                Start-Sleep -Seconds $POLL_INTERVAL_SEC
            }
        }
    }
}


function Invoke-FabricCapacityAction {
    param(
        [string]$SubscriptionId,
        [string]$ResourceGroup,
        [string]$CapacityName,
        [ValidateSet('resume','suspend')]
        [string]$Action,
        [string]$Token
    )

    $endpoint = "https://management.azure.com/subscriptions/$SubscriptionId" +
                "/resourceGroups/$ResourceGroup" +
                "/providers/Microsoft.Fabric/capacities/$CapacityName/$Action" +
                "?api-version=$API_VERSION"

    $headers = @{
        Authorization  = "Bearer $Token"
        'Content-Type' = 'application/json'
    }

    Write-Host "[INFO] Enviando petición '$Action' a la capacidad '$CapacityName'..."
    Write-Host "[DEBUG] Endpoint: $endpoint"

    try {
        $resp = Invoke-WebRequest -Method Post -Uri $endpoint -Headers $headers -TimeoutSec 30 -SkipHttpErrorCheck
    }
    catch {
        throw "Error de red al ejecutar la acción '$Action': $($_.Exception.Message)"
    }

    $statusCode = [int]$resp.StatusCode

    if ($statusCode -eq 200) {
        Write-Host '[OK] Operación completada de forma inmediata (HTTP 200).'
        return
    }

    if ($statusCode -eq 202) {
        $pollingUrl = $resp.Headers['Azure-AsyncOperation']
        if (-not $pollingUrl) { $pollingUrl = $resp.Headers['Location'] }

        if (-not $pollingUrl) {
            throw "La API devolvió 202 (asíncrono), pero no incluyó cabecera 'Azure-AsyncOperation' ni 'Location' para hacer polling."
        }

        # Invoke-WebRequest devuelve arrays para cabeceras multi-valor; tomamos el primero
        if ($pollingUrl -is [array]) { $pollingUrl = $pollingUrl[0] }

        Invoke-AsyncPolling -PollingUrl $pollingUrl -Headers $headers
        return
    }

    throw "Error al ejecutar acción sobre la capacidad. HTTP $statusCode. Respuesta: $($resp.Content)"
}


# ==============================
# Punto de entrada
# ==============================
Write-Host '[INFO] Inicio de ejecución del script de control de capacidad Fabric.'

try {
    $token = Get-FabricToken -TenantId $TENANT_ID -ClientId $CLIENT_ID -ClientSecret $CLIENT_SECRET

    Invoke-FabricCapacityAction `
        -SubscriptionId $SUBSCRIPTION_ID `
        -ResourceGroup  $RESOURCE_GROUP `
        -CapacityName   $CAPACITY_NAME `
        -Action         $ACTION `
        -Token          $token

    Write-Host '[OK] Proceso finalizado con éxito.'
    exit 0
}
catch {
    Write-Host "[ERROR] $($_.Exception.Message)"
    exit 1
}
