# Netatmo Presence para Home Assistant

Integración personalizada para la cámara exterior **Netatmo Presence** (Smart Outdoor Camera, modelo NOC):

- **Foco con brillo** (0–100 %), encendido, apagado y modo automático.
- **Sensores de movimiento**: movimiento, persona, animal y vehículo.
- **Disparadores nocturnos**: qué detecciones encienden el foco de noche en modo automático.

El foco se controla **por la red local** cuando Home Assistant está en la misma red que la cámara. Si no, usa el relé de Netatmo. La integración oficial de Netatmo no permite cambiar el brillo; esta sí.

> Proyecto no oficial, sin relación con Netatmo ni Legrand. El control local usa una API de la cámara que Netatmo no documenta: un firmware futuro podría cambiarla.

*[English below](#english)*

## Entidades (por cámara)

| Entidad | Tipo | Qué hace |
|---|---|---|
| Foco | `light` | Encender con brillo. Al apagar vuelve a *Automático* (o a *Apagado*, según las opciones). |
| Modo del foco | `select` | Encendido / Apagado / Automático. |
| Intensidad del foco | `number` | Cambia el brillo sin cambiar el modo, así que también vale para el modo automático. |
| Movimiento, Persona, Animal, Vehículo | `binary_sensor` | Se activan con cada detección y se apagan solos a los 30 s (configurable). |
| Noche: encender con persona / vehículo / animal / cualquier movimiento / siempre encendido | `switch` | Lo mismo que en la app de Netatmo. |

Cada detección lanza además un evento `netatmo_presence_event` con `camera_id`, `camera_name`, `type` (`human`, `animal`, `vehicle` o `movement`) y `source` (`webhook` o `poll`).

En modo *Automático*, la entidad Foco aparece apagada aunque el foco se haya encendido solo por una detección: la cámara no informa de eso.

## Instalación

### HACS (recomendado)
1. HACS → menú ⋮ → **Repositorios personalizados**. Añade `https://github.com/xcrittpm/ha-netatmo-presence`, categoría **Integración**.
2. Instala **Netatmo Presence** y reinicia Home Assistant.

### Manual
Copia `custom_components/netatmo_presence` en la carpeta `config/custom_components/` de Home Assistant y reinicia.

## Configuración

1. En [dev.netatmo.com/apps](https://dev.netatmo.com/apps) crea una app nueva.
   - **Redirect URI:** `https://my.home-assistant.io/redirect/oauth`
   - Usa una app **exclusiva** para esta integración. Netatmo solo permite un webhook por app: si la compartes con la integración oficial de Netatmo, una de las dos dejará de recibir eventos.
2. En Home Assistant: **Ajustes → Dispositivos y servicios → Añadir integración → Netatmo Presence**.
3. Escribe el *client ID* y el *client secret* de la app, e inicia sesión en Netatmo.

### Movimiento al instante (webhook)
Para recibir las detecciones al momento, Netatmo tiene que poder llamar a Home Assistant:
- con **Home Assistant Cloud (Nabu Casa)**, funciona solo; o
- con una URL externa **HTTPS en el puerto 443** configurada en *Ajustes → Sistema → Red*.

Si no, la integración consulta los eventos en cada actualización (cada 60 s por defecto), con ese retraso. En el registro aparece `Netatmo webhook active` cuando el webhook funciona.

### Opciones
- **Al apagar la luz, pasar a:** *Automático* (por defecto) o *Apagado*.
- **Los sensores de movimiento siguen activos durante:** segundos (30 por defecto).
- **Intervalo de consulta:** segundos (60 por defecto). Netatmo limita a unas 500 peticiones por hora y por usuario.
- **Recibir el movimiento al instante (webhook):** activado por defecto.

## Privacidad
- Los tokens los guarda Home Assistant. Esta integración no los envía a ningún sitio salvo a Netatmo.
- Las URL de la cámara llevan claves de acceso. La integración no las escribe en el registro y las tapa en los diagnósticos.

---

## English

Custom integration for the **Netatmo Presence** outdoor camera: floodlight **with brightness**, motion sensors (any motion, person, animal, vehicle) and the night trigger switches. The floodlight is controlled over the **local network** when possible, with Netatmo's relay as a fallback.

**Setup:** install via HACS (custom repository, category *Integration*) or copy `custom_components/netatmo_presence`. Create a dedicated app at [dev.netatmo.com/apps](https://dev.netatmo.com/apps) with redirect URI `https://my.home-assistant.io/redirect/oauth`, then add the integration and enter the app's client ID and secret. Real-time motion needs Home Assistant Cloud or an external HTTPS URL on port 443; otherwise events are polled.

Unofficial project, not affiliated with Netatmo or Legrand. The local floodlight API is undocumented and may change with firmware updates.

## Licencia / License
MIT
