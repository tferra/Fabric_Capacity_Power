#!/usr/bin/env python3
"""
Script para encender (resume) o apagar (suspend) una capacidad de Microsoft Fabric
usando autenticación por Service Principal (OAuth2 client credentials flow).

Requisitos:
- requests
"""

import sys
import time
from typing import Optional

import requests


# ==============================
# Variables de configuración
# ==============================
TENANT_ID = "TU_TENANT_ID"
CLIENT_ID = "TU_CLIENT_ID"
CLIENT_SECRET = "CAMBIAR_ESTE_VALOR"
SUBSCRIPTION_ID = "TU_SUBSCRIPTION_ID"
RESOURCE_GROUP = "TU_RESOURCE_GROUP"
CAPACITY_NAME = "TU_CAPACITY_NAME"

ACTION = "suspend"  # "resume" para encender, "suspend" para apagar


# ==============================
# Constantes
# ==============================
ARM_SCOPE = "https://management.azure.com/.default"
TOKEN_URL_TEMPLATE = "https://login.microsoftonline.com/{tenant_id}/oauth2/v2.0/token"
API_VERSION = "2023-11-01"
POLL_INTERVAL_SECONDS = 10
POLL_TIMEOUT_SECONDS = 1800  # 30 minutos


class ScriptError(Exception):
    """Excepción controlada para errores del flujo del script."""


def obtener_token(tenant_id: str, client_id: str, client_secret: str) -> str:
    """Obtiene un access token de Azure AD usando client credentials flow."""
    print("[INFO] Autenticando con Azure AD (client credentials)...")

    token_url = TOKEN_URL_TEMPLATE.format(tenant_id=tenant_id)
    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "scope": ARM_SCOPE,
        "grant_type": "client_credentials",
    }

    try:
        response = requests.post(token_url, data=payload, timeout=30)
    except requests.RequestException as exc:
        raise ScriptError(f"Error de red al solicitar token: {exc}") from exc

    if response.status_code != 200:
        detalle = response.text.strip()
        raise ScriptError(
            "Error de autenticación. "
            f"HTTP {response.status_code}. Respuesta: {detalle}"
        )

    try:
        token_data = response.json()
    except ValueError as exc:
        raise ScriptError("Respuesta de token no es JSON válido.") from exc

    access_token = token_data.get("access_token")
    if not access_token:
        raise ScriptError("No se recibió 'access_token' en la respuesta de autenticación.")

    print("[OK] Token obtenido correctamente.")
    return access_token


def extraer_estado_desde_respuesta(response: requests.Response) -> Optional[str]:
    """Intenta extraer un estado de operación desde distintos formatos JSON de ARM."""
    try:
        data = response.json()
    except ValueError:
        return None

    if isinstance(data, dict):
        # Formatos comunes en ARM:
        # {"status": "InProgress|Succeeded|Failed"}
        # {"properties": {"provisioningState": "..."}}
        status = data.get("status")
        if isinstance(status, str):
            return status

        properties = data.get("properties")
        if isinstance(properties, dict):
            provisioning_state = properties.get("provisioningState")
            if isinstance(provisioning_state, str):
                return provisioning_state

    return None


def hacer_polling(
    polling_url: str,
    headers: dict,
    intervalo_segundos: int = POLL_INTERVAL_SECONDS,
    timeout_segundos: int = POLL_TIMEOUT_SECONDS,
) -> None:
    """Realiza polling sobre la URL de operación asíncrona hasta finalizar."""
    print(f"[INFO] Operación asíncrona detectada. Iniciando polling en: {polling_url}")

    inicio = time.time()
    intento = 0

    while True:
        if (time.time() - inicio) > timeout_segundos:
            raise ScriptError(
                f"Timeout tras {timeout_segundos} segundos esperando la operación asíncrona."
            )

        intento += 1
        print(f"[INFO] Polling intento #{intento}...")

        try:
            response = requests.get(polling_url, headers=headers, timeout=30)
        except requests.RequestException as exc:
            raise ScriptError(f"Error de red durante polling: {exc}") from exc

        if response.status_code >= 400:
            detalle = response.text.strip()
            raise ScriptError(
                "Error HTTP durante polling. "
                f"HTTP {response.status_code}. Respuesta: {detalle}"
            )

        estado = extraer_estado_desde_respuesta(response)

        # ARM puede devolver 202 mientras sigue en curso.
        # Si no hay estado explícito y sigue 202, asumimos en progreso.
        if response.status_code == 202 and not estado:
            estado = "InProgress"

        if not estado:
            # En algunos casos Location puede acabar con 200 sin payload estándar.
            if response.status_code == 200:
                print("[OK] Polling finalizado con HTTP 200.")
                return

            print(
                "[WARN] No se pudo determinar estado en esta iteración; "
                f"HTTP {response.status_code}. Se reintenta..."
            )
            time.sleep(intervalo_segundos)
            continue

        estado_normalizado = estado.strip().lower()
        print(f"[INFO] Estado actual: {estado}")

        if estado_normalizado == "succeeded":
            print("[OK] Operación completada correctamente (Succeeded).")
            return

        if estado_normalizado == "failed":
            detalle = response.text.strip()
            raise ScriptError(f"La operación finalizó en Failed. Detalle: {detalle}")

        if estado_normalizado == "canceled":
            raise ScriptError("La operación fue cancelada (Canceled).")

        # Cualquier otro estado lo tratamos como en progreso.
        print(f"[INFO] Esperando {intervalo_segundos} segundos antes del siguiente polling...")
        time.sleep(intervalo_segundos)


def ejecutar_accion(
    subscription_id: str,
    resource_group: str,
    capacity_name: str,
    action: str,
    token: str,
) -> None:
    """Ejecuta la acción resume/suspend sobre la capacidad de Fabric."""
    action_normalizada = action.strip().lower()
    if action_normalizada not in ("resume", "suspend"):
        raise ScriptError("ACTION debe ser 'resume' o 'suspend'.")

    endpoint = (
        f"https://management.azure.com/subscriptions/{subscription_id}"
        f"/resourceGroups/{resource_group}"
        f"/providers/Microsoft.Fabric/capacities/{capacity_name}/{action_normalizada}"
        f"?api-version={API_VERSION}"
    )

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    print(f"[INFO] Enviando petición '{action_normalizada}' a la capacidad '{capacity_name}'...")
    print(f"[DEBUG] Endpoint: {endpoint}")

    try:
        response = requests.post(endpoint, headers=headers, timeout=30)
    except requests.RequestException as exc:
        raise ScriptError(f"Error de red al ejecutar la acción '{action_normalizada}': {exc}") from exc

    if response.status_code == 200:
        print("[OK] Operación completada de forma inmediata (HTTP 200).")
        return

    if response.status_code == 202:
        polling_url = response.headers.get("Azure-AsyncOperation") or response.headers.get("Location")
        if not polling_url:
            raise ScriptError(
                "La API devolvió 202 (asíncrono), pero no incluyó cabecera "
                "'Azure-AsyncOperation' ni 'Location' para hacer polling."
            )

        hacer_polling(polling_url=polling_url, headers=headers)
        return

    detalle = response.text.strip()
    raise ScriptError(
        "Error al ejecutar acción sobre la capacidad. "
        f"HTTP {response.status_code}. Respuesta: {detalle}"
    )


def main() -> int:
    """Punto de entrada principal del script."""
    print("[INFO] Inicio de ejecución del script de control de capacidad Fabric.")

    try:
        token = obtener_token(
            tenant_id=TENANT_ID,
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
        )

        ejecutar_accion(
            subscription_id=SUBSCRIPTION_ID,
            resource_group=RESOURCE_GROUP,
            capacity_name=CAPACITY_NAME,
            action=ACTION,
            token=token,
        )

        print("[OK] Proceso finalizado con éxito.")
        return 0

    except ScriptError as exc:
        print(f"[ERROR] {exc}")
        return 1
    except Exception as exc:  # Captura defensiva para errores inesperados.
        print(f"[ERROR] Error inesperado: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
