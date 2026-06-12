# Control de capacidad Microsoft Fabric (Script + Notebook)

Este proyecto incluye **dos implementaciones equivalentes** para encender o apagar una capacidad de Microsoft Fabric mediante la API REST de Azure Resource Manager y autenticación de Service Principal (OAuth2 client credentials flow).

Los dos archivos hacen lo mismo y mantienen la misma estructura lógica:

- `fabric_capacity_power.py` (formato script de Python)
- `NT_fabric_capacity_power.ipynb` (formato notebook para Microsoft Fabric)

## Objetivo

Permitir ejecutar una acción sobre una capacidad de Fabric:

- `resume`: encender la capacidad
- `suspend`: apagar la capacidad

## Requisitos

- Python 3.9+ (recomendado)
- Librería `requests`

Instalación de dependencia:

```bash
pip install requests
```

## Configuración

En ambos archivos, al inicio se definen las mismas variables de configuración:

- `TENANT_ID`: ID del tenant de Azure AD
- `CLIENT_ID`: client ID del Service Principal
- `CLIENT_SECRET`: client secret del Service Principal
- `SUBSCRIPTION_ID`: ID de la suscripción de Azure
- `RESOURCE_GROUP`: nombre del Resource Group
- `CAPACITY_NAME`: nombre de la capacidad de Microsoft Fabric
- `ACTION`: `"resume"` o `"suspend"`

## Estructura común (en ambos formatos)

Los dos ficheros comparten la misma lógica separada por funciones:

1. `obtener_token(...)`
- Solicita el token OAuth2 a Azure AD usando client credentials.

2. `ejecutar_accion(...)`
- Llama al endpoint REST de ARM para `resume` o `suspend`.

3. `hacer_polling(...)`
- Gestiona operaciones asíncronas cuando la API responde `202 Accepted`.
- Usa la cabecera `Azure-AsyncOperation` o `Location` para consultar estado hasta `Succeeded` o `Failed`.

4. Manejo de errores
- Captura errores de autenticación, errores HTTP y errores de red.
- Muestra mensajes claros en consola/salida de notebook.

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

### Opción 2: Notebook de Microsoft Fabric

1. Abre `NT_fabric_capacity_power.ipynb`.
2. Ajusta las variables de configuración en la celda correspondiente.
3. Ejecuta las celdas en orden hasta completar la acción.

## Salida esperada

Durante la ejecución se muestran estados como:

- autenticando
- enviando petición
- operación asíncrona detectada
- polling en progreso
- operación completada (`Succeeded`) o error (`Failed`)

## Notas de seguridad

- No compartas ni subas `CLIENT_SECRET` a repositorios públicos.
- Considera usar secretos gestionados (por ejemplo, variables seguras o Key Vault) para entornos productivos.
