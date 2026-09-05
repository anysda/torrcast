[English](../README.md) | [日本語](README-jp.md) | [Русский](README-ru.md)

# torrcast

**Pon una película en el televisor con solo escribir su título.**

Alguien te recomienda Matrix durante el día. Lo que viene después suele ser un engorro: recorrer el catálogo de una plataforma de streaming, descargar la película de antemano o escribir el título en el navegador del televisor con el mando. torrcast es para cuando ya sabes qué quieres ver. Esa noche escribes `cast matrix` y la película empieza en el televisor, sin pelearte con la interfaz.

torrcast busca películas, series y anime, elige una versión que se pueda reproducir y una pista de audio, y transmite el vídeo a Chromecast. Puedes iniciar la reproducción desde la terminal, Telegram o Home Assistant.

[Instalación](#instalación) · [Ver películas y series](#ver-películas-y-series) · [Home Assistant](#home-assistant) · [Telegram](#telegram) · [Comandos](#comandos)

![Demostración de la instalación de torrcast y la reproducción de una película](https://raw.githubusercontent.com/anysda/torrcast/master/docs/demo.gif)

- **Sigue viendo.** Los episodios se reproducen uno tras otro. Al terminar una temporada, torrcast busca la siguiente. Puedes dejarlo por hoy y continuar mañana desde donde lo dejaste.
- **Conserva tu audio preferido.** La pista se selecciona según el idioma que hayas elegido para torrcast. Si eliges otra pista u otro estudio, recordará tu elección para ese título.
- **Precarga mientras ves la película.** torrcast guarda la película en caché en segundo plano. Cuando avise de que ya está entera en el disco, podrás terminar de verla y avanzar o retroceder sin conexión a internet. El ordenador y el televisor siguen necesitando la conexión local entre ellos.
- **Deja el formato en manos de torrcast.** Convierte el vídeo cuando el receptor lo necesita y te va avisando de los cambios de versión, audio o calidad.

## Qué necesitas

| Componente | Requisito |
| --- | --- |
| Televisor | Un receptor Chromecast integrado en el televisor o en un dispositivo de streaming conectado a él. |
| Ordenador<br>(preferiblemente&nbsp;un&nbsp;servidor) | Debian 12 o posterior, o Ubuntu, con systemd; también macOS. La instalación nativa en Mac se ha probado en Apple Silicon. |
| Almacenamiento | Unos 33 GB libres para la precarga y una reserva para el sistema; deja espacio adicional para las dependencias y la caché de streaming. |
| Red | Acceso a internet y una red doméstica de confianza a la que estén conectados tanto el ordenador como el receptor. |

torrcast está pensado para funcionar de forma continua en un servidor doméstico, una máquina virtual o un contenedor LXC, listo cuando quieras ver algo. También puedes ejecutarlo en un Mac; evita que el ordenador entre en reposo durante la reproducción. Si usas una máquina virtual o un contenedor, comprueba que pueda comunicarse con el receptor por la red local en ambos sentidos. El vídeo viaja desde ese ordenador hasta el televisor por la red local.

## Instalación

Ejecuta esto en el ordenador que enviará el vídeo al televisor:

```sh
curl -fsSL https://torrcast.anysda.space | sh
```

El instalador descarga la última versión, comprueba su suma de verificación SHA-256, instala las dependencias y configura los servicios en segundo plano. Solicita permisos de administrador cuando los necesita y configura el receptor automáticamente si encuentra uno solo. La instalación queda en inglés; `cast --ru` cambia el idioma guardado, incluidos los mensajes de la terminal, las respuestas del bot y las preferencias de audio, y `cast --en` lo devuelve al inglés.

Ahora pon una película:

```sh
cast matrix
```

Si se han encontrado varios receptores, elige uno con `cast --tv` y vuelve a ejecutar el comando de la película. También puedes indicar una dirección directamente con `cast --tv <ip>`.

<details>
<summary>Instalación en macOS</summary>

El mismo comando de una línea permite instalar torrcast de forma nativa en macOS. Ejecútalo desde tu cuenta habitual con permisos de administrador. El instalador se ocupa de instalar Homebrew si hace falta y utiliza launchd para los servicios en segundo plano.

La reproducción se ejecuta como root para acceder a la red local desde un servicio en segundo plano. El instalador añade para el usuario que realiza la instalación una regla de sudo sin contraseña, limitada al comando `cast`. Puedes seguir poniendo películas con `cast matrix`.

El script inicial necesita `sha256sum` antes de llegar a la instalación de Homebrew. Si se detiene con el mensaje `sha256sum is required but is not in PATH`, utiliza la instalación desde el repositorio que se describe a continuación: ejecuta `install.sh` directamente. Si macOS pregunta si quieres permitir conexiones entrantes, acéptalas para que el receptor pueda acceder al flujo de vídeo.

</details>

<details>
<summary>Instalación desde el repositorio</summary>

```sh
git clone https://github.com/anysda/torrcast
cd torrcast
./install.sh
```

Aquí el instalador también se encarga de las dependencias y los permisos de administrador. En Linux sobre ARM, debe haber una versión funcional de ffmpeg 6.1 o posterior si la distribución no la proporciona; la compilación de Linux que el instalador ofrece como alternativa es para x86_64.

</details>

## Ver películas y series

Normalmente basta con el título. Añade `--menu` para elegir tú la película, por ejemplo, cuando la búsqueda encuentre varias entregas de una saga:

```console
$ cast matrix --menu
  1. Matrix (1999) · IMDb 8.7 · 2 h 16 min
     Película de acción y ciencia ficción escrita y dirigida por las Wachowski.
  2. Matrix Reloaded (2003) · IMDb 7.2 · 2 h 18 min
     Película de acción y ciencia ficción, segunda entrega de la saga Matrix.
  3. Matrix Revolutions (2003) · IMDb 6.7 · 2 h 9 min
     Película de acción y ciencia ficción, tercera entrega de la saga Matrix.
Enter - «Matrix (1999)», opción 1 de 3
¿Qué vamos a ver? [1]:
```

Pulsa Enter para reproducir la película indicada como opción predeterminada o escribe un número. Los resultados, las puntuaciones y las versiones disponibles pueden cambiar. torrcast agrupa las versiones de una misma película: tú eliges la película una sola vez y el programa se encarga de seleccionar la versión que va a reproducir.

Para una serie, añade la temporada y el episodio:

```sh
cast kim possible s1e1
```

El siguiente episodio empieza automáticamente. `cast stop` guarda el punto en el que te quedaste, y **`cast` sin argumentos reanuda la última serie**. Para continuar una película, vuelve a pedirla por su título.

Puedes pausar, avanzar y retroceder con el mando del televisor. Una vez iniciada la reproducción, puedes cerrar la terminal o desconectar la sesión SSH. torrcast gestiona la caché automáticamente; no hay ninguna biblioteca multimedia que organizar.

## Home Assistant

Añade torrcast a tu panel: podrás poner una película, pausar, avanzar o retroceder, ajustar el volumen o pasar al siguiente episodio. La integración se conecta a torrcast a través de tu red local.

[![Añadir torrcast a HACS](https://my.home-assistant.io/badges/hacs_repository.svg)](https://my.home-assistant.io/redirect/hacs_repository/?owner=anysda&repository=torrcast&category=integration)

1. Instala torrcast con el comando anterior y utiliza el botón para añadir su [repositorio personalizado en HACS](https://www.hacs.xyz/docs/faq/custom_repositories/) y descargar la integración.
2. Reinicia Home Assistant. En **Ajustes > Dispositivos y servicios**, confirma el dispositivo torrcast detectado. Si no aparece, añade la integración de torrcast manualmente con la dirección IP del ordenador y el puerto `8479`.
3. Añade su reproductor multimedia al panel. Abre el navegador multimedia: **instant** permite introducir un título e iniciar la reproducción; **menu** busca y te deja elegir un resultado.

Assist también puede controlar la reproducción. Iniciar una película por su título depende de los idiomas que admita el asistente: en la configuración probada, Assist integrado admite esa petición en inglés, pero no en ruso. Los títulos en ruso se pueden introducir en el navegador multimedia independientemente de esa limitación del control por voz.

## Telegram

Envía `cast matrix` desde el sofá y controla la reproducción con los botones del chat. El bot muestra el progreso mientras se inicia la película y después ofrece controles de pausa, parada, volumen y saltos de 30 segundos hacia delante o hacia atrás. También controla la reproducción iniciada desde la terminal o Home Assistant.

Configúralo en el ordenador donde está instalado torrcast:

```sh
cast -tg
```

Crea un bot con [BotFather](https://core.telegram.org/bots/features#botfather), abre un chat con él y pulsa **Iniciar**. En el menú de configuración, introduce el token del bot y el ID de tu chat, y elige **Test and save** (probar y guardar). La configuración envía un mensaje de prueba y activa el servicio del bot, que vuelve a iniciarse después de reiniciar el ordenador. El bot solo acepta comandos del chat configurado.

<details>
<summary>Cómo encontrar el ID de tu chat</summary>

Antes de activar el servicio del bot, envía un mensaje a tu nuevo bot. Abre `https://api.telegram.org/bot<TOKEN>/getUpdates` en un navegador y sustituye `<TOKEN>` por el token de BotFather. En la [respuesta](https://core.telegram.org/bots/api#getupdates), copia el número de `result[].message.chat.id` en el campo **Chat ID** (ID del chat) del menú de configuración.

</details>

Envía estos comandos como mensajes normales:

```text
cast matrix
cast kim possible s1e1
cast
cast stop
```

El teléfono envía los comandos a través de Telegram; el flujo de vídeo se mantiene entre el ordenador y el televisor.

## Comandos

| Comando | Acción |
| --- | --- |
| `cast <título>` | Buscar una película o serie y reproducirla. |
| `cast <título> s1e1` | Reproducir un episodio concreto indicando la temporada y el número de episodio. |
| `cast` | Reanudar la última serie. |
| `cast stop` | Detener la reproducción y guardar la posición. |
| `cast status` | Mostrar qué se está reproduciendo, la posición y el progreso de la precarga. |
| `cast <título> --menu` | Mostrar los títulos encontrados y preguntar cuál reproducir, en lugar de empezar directamente. |
| `cast <título> --pick N` | Reproducir el título N del menú sin preguntar. |
| `cast <título> --new` | Reproducir desde el principio la misma versión, con el mismo archivo y la misma pista de audio. |
| `cast <título> --voice` | Elegir una pista de audio en un menú. `--voice N` o `--voice ESTUDIO` la selecciona y guarda la elección. |
| `cast voices <título>` | Mostrar las pistas disponibles antes de iniciar la reproducción. |
| `cast releases <título>` | Listar las versiones agrupadas por título. `--release N` con la misma búsqueda reproduce la versión indicada. |
| `cast <título> --dry` | Realizar todo el proceso de selección sin transmitir al televisor. |
| `cast --tv` | Buscar receptores en la red y elegir uno. `cast --tv <ip>` fija la dirección directamente. |
| `cast -tg` | Abrir el menú de configuración del bot de Telegram. |
| `cast --ru` / `cast --en` | Cambiar el idioma y guardar la elección. |
| `cast doctor` | Comprobar los servicios, la red y el receptor. |
| `cast log --since 2d` | Consultar el registro de diagnóstico. `--since` acepta `2d`, `12h`, `30m` o una fecha en formato `AAAA-MM-DD`. |
| `cast --upgrade` | Actualizar a la última versión. |
| `cast --version` | Mostrar la versión. |
| `cast -h` | Ver todos los comandos y opciones. |

## Actualizaciones y ayuda

```sh
cast --upgrade
```

Las actualizaciones conservan tus ajustes y el receptor elegido. El actualizador no se ejecuta mientras se está reproduciendo algo.

Si una película no arranca, ejecuta `cast doctor` para comprobar los servicios, la red y el receptor. `cast log --since 2h` muestra los eventos recientes de reproducción; `cast -h` enumera los comandos y las opciones.

Para comunicar un error, [abre una incidencia](https://github.com/anysda/torrcast/issues) e incluye el comando que ejecutaste, tu sistema operativo, el modelo del receptor y la salida de diagnóstico pertinente.

## Licencia y responsabilidad

El código de torrcast se distribuye bajo la licencia [MIT](https://github.com/anysda/torrcast/blob/master/LICENSE). La licencia cubre únicamente el código y no otorga ningún derecho sobre lo que veas con él: las fuentes y su legalidad son responsabilidad del usuario.
