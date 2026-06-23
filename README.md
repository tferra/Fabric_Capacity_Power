# Control de capacidad Microsoft Fabric (Script + Notebook)

Este proyecto incluye **tres implementaciones equivalentes** para encender o apagar una capacidad de Microsoft Fabric mediante la API REST de Azure Resource Manager y autenticación de Service Principal (OAuth2 client credentials flow).

Los tres archivos hacen lo mismo y mantienen la misma estructura lógica:

- `fabric_capacity_power.py` (script Python)
- `fabric_capacity_power.ps1` (script PowerShell 7+)
- `NT_fabric_capacity_power.ipynb` (notebook para Microsoft Fabric)

## Objetivo

Permitir ejecutar una acción sobre una capacidad de Fabric:

- `resume`: encender la capacidad
- `suspend`: apagar la capacidad

## Requisitos

### Python

- Python 3.9+
- Librería `requests`

```bash
pip install requests
```

### PowerShell

- PowerShell 7.0+ (`pwsh`)
- Sin dependencias adicionales (usa `Invoke-RestMethod` e `Invoke-WebRequest` nativos)

### Notebook

- Entorno Microsoft Fabric con acceso al notebook

## Configuración

En los tres archivos, al inicio se definen las mismas variables de configuración:

| Variable | Descripción |
|---|---|
| `TENANT_ID` | ID del tenant de Azure AD |
| `CLIENT_ID` | Client ID del Service Principal |
| `CLIENT_SECRET` | Client secret del Service Principal |
| `SUBSCRIPTION_ID` | ID de la suscripción de Azure |
| `RESOURCE_GROUP` | Nombre del Resource Group |
| `CAPACITY_NAME` | Nombre de la capacidad de Microsoft Fabric |
| `ACTION` | `resume` o `suspend` |

## Estructura común (en los tres formatos)

Los tres ficheros comparten la misma lógica separada en funciones equivalentes:

| Python | PowerShell | Descripción |
|---|---|---|
| `obtener_token()` | `Get-FabricToken` | Solicita el token OAuth2 a Azure AD usando client credentials |
| `ejecutar_accion()` | `Invoke-FabricCapacityAction` | Llama al endpoint REST de ARM para `resume` o `suspend` |
| `hacer_polling()` | `Invoke-AsyncPolling` | Gestiona operaciones asíncronas cuando la API responde `202 Accepted` |
| `extraer_estado_desde_respuesta()` | `Get-OperationStatus` | Extrae el estado de la respuesta ARM (`status` o `provisioningState`) |

El polling usa la cabecera `Azure-AsyncOperation` o `Location` para consultar el estado hasta `Succeeded` o `Failed`.

## Endpoints REST usados

Con `api-version=2023-11-01`:

- Encender:

```text
POST https://management.azure.com/subscriptions/{subscriptionId}/resourceGroups/{resourceGroup}/providers/Microsoft.Fabric/capacities/{capacityName}/resume?api-version=2023-11-01
```

- Apagar:

```text
POST https://management.azure.com/subscriptions/{subscriptionId}/resourceGroups/{resourceGroup}/providers/Microsoft.Fabric/capacities/{capacityName}/suspend?api-version=2023-11-01
```

## Ejecución

### Opción 1: Script Python

1. Edita las variables de configuración al inicio de `fabric_capacity_power.py`.
2. Ejecuta:

```bash
python fabric_capacity_power.py
```

### Opción 2: Script PowerShell

1. Edita las variables de configuración al inicio de `fabric_capacity_power.ps1`.
2. Ejecuta:

```powershell
pwsh .\fabric_capacity_power.ps1
```

### Opción 3: Notebook de Microsoft Fabric

1. Abre `NT_fabric_capacity_power.ipynb`.
2. Ajusta las variables de configuración en la celda correspondiente.
3. Ejecuta las celdas en orden hasta completar la acción.

## Salida esperada

Durante la ejecución se muestran estados como:

```
[INFO] Inicio de ejecución del script de control de capacidad Fabric.
[INFO] Autenticando con Azure AD (client credentials)...
[OK] Token obtenido correctamente.
[INFO] Enviando petición 'suspend' a la capacidad 'mi-capacidad'...
[INFO] Operación asíncrona detectada. Iniciando polling en: https://...
[INFO] Polling intento #1...
[INFO] Estado actual: InProgress
[INFO] Polling intento #2...
[OK] Operación completada correctamente (Succeeded).
[OK] Proceso finalizado con éxito.
```

## Notas de seguridad

- No compartas ni subas `CLIENT_SECRET` a repositorios públicos.
- Considera usar secretos gestionados (por ejemplo, variables seguras de entorno o Azure Key Vault) para entornos productivos.
