[English](../README.md) | [日本語](README-jp.md) | [Русский](README-ru.md)

# torrcast

**Dices el nombre de una película y ya se está reproduciendo en el televisor.**

> **Nota sobre el idioma.** El producto todavía no habla español: la interfaz, los mensajes
> y la selección de pista de audio existen solo en inglés y en ruso. El instalador de un
> solo comando pone la compilación **en inglés**, y esta página es únicamente una
> traducción de la documentación.

Un comando en la terminal encuentra una película, una serie o un anime por su nombre y lo
pone en el televisor. Sin nube en la ruta de los datos, sin biblioteca multimedia ni colas
de descarga, sin ir escogiendo releases y pistas de audio a mano. El flujo va directo: del
enjambre a tu servidor y de ahí al televisor. No hay terceros entre tú y la imagen.

<p align="center">
  <img src="demo.gif" alt="Instalación de torrcast y ejecución de cast: del comando a la imagen en el televisor">
</p>

## Qué aspecto tiene

```console
$ cast matrix --menu
searching “matrix”... 2.4 s
  1. The Matrix (1999) · IMDb 8.7 · 2 h 16 min
     The Matrix is a 1999 science fiction action film written and directed by the
     Wachowskis.
  2. The Matrix Reloaded (2003) · IMDb 7.2 · 2 h 18 min
     ...
  3. The Matrix Revolutions (2003) · IMDb 6.7 · 2 h 9 min
     ...
Enter - “The Matrix (1999)”, item 1 of 3
What are we watching? [1]:
looking for an English voice: release 1 of 47 - tracks... 2.3 s
packing... 3.1 s
waiting for the TV... 1.2 s
playing “The Matrix” (1999) · 1080p · eng · Original - on TV   (start 9 s)
```

Sin `--menu` no hay pregunta alguna: torrcast toma la película con el enjambre más vivo y
la nombra en voz alta en una sola línea. `start 9 s` es el tiempo hasta el primer fotograma
real en la pantalla, no hasta el momento en que el receptor se declara listo. A partir de
ahí manda el mando otra vez: la pausa y el salto funcionan como con cualquier otra fuente.
La ejecución está abreviada, porque los números de release, los seeders y los tiempos
cambian con las respuestas de los indexadores y del enjambre.

## Por qué resulta cómodo

- **Un solo comando.** Lo pides y se reproduce. Sin elegir release, sin cola de descargas,
  sin administrar pistas de audio. A menudo, sin una sola pregunta.
- **Las series avanzan solas.** El siguiente episodio arranca sin preguntar y sin volver a
  conectarse al televisor. Si la temporada termina, torrcast busca la siguiente por su
  cuenta y sigue desde su primer episodio. Si la serie termina, lo dice con honestidad.
- **La pista de audio se elige sola.** Según el idioma del producto: una instalación en
  inglés pone primero las pistas en inglés; una en ruso, las rusas.
  `cast <consulta> --voice ESTUDIO` recuerda para siempre la voz preferida de esa película.
- **Internet puede caerse; la película, no.** Mientras ves, la película se precarga entera
  en el disco en segundo plano. Terminada la precarga, la ves hasta el final sin red
  alguna, saltos incluidos.
- **Nada de más en el disco.** La caché vive exactamente lo que dura la reproducción. No
  hay biblioteca multimedia ni "algún día habrá que limpiar esto".
- **La fluidez por encima de las cifras.** Si el release pesa demasiado para el receptor,
  los trozos pesados se transcodifican al vuelo. La calidad se sacrifica en último lugar y
  solo lo justo para que no haya pausas de búfer.
- **Habla inglés y ruso.** `cast --en` y `cast --ru` cambian el producto entero: los
  rótulos, los mensajes, las respuestas del bot y la pista de audio que va a buscar.
- **Bot de Telegram.** `cast -tg`, y el televisor se maneja desde un chat. La
  configuración deja el bot como servicio, así que el chat responde también tras
  reiniciar.
- **Honesto.** Ni una sustitución silenciosa. Cada decisión automática tiene su línea
  clara:

```text
release 1 actually 574p - taking 2 (actually 1080p)
attention: ~36 Mbit/s - heavy chunks get recoded on the fly
video hevc - recoding it whole on the fly
```

## Lo que torrcast no es

- **No es un gestor de descargas de torrents.** En el disco solo está lo que se reproduce,
  y solo mientras se reproduce.
- **No es un servidor multimedia.** No hay biblioteca, ni interfaz web, ni cuentas. Hay un
  comando.
- **No es un servicio en la nube.** Ningún servidor ajeno en la ruta del flujo: la
  dirección para el televisor se deduce de la ruta hasta él, y el DNS no interviene en la
  ruta de reproducción.

## Instalación

```sh
curl -fsSL https://torrcast.anysda.space | sh
```

Esta es la versión en inglés; la rusa la instala `https://rutorrcast.anysda.space`. La
elección no es definitiva en ningún sentido: `cast --en` y `cast --ru` cambian una copia ya
instalada en cualquier momento. El comando de una línea pregunta a GitHub por la última
versión, descarga el tarball exactamente de esa versión, comprueba su suma SHA-256 y es
idempotente: una segunda ejecución actualiza solo lo que ha cambiado. No hacen falta ni
registro ni claves de API externas.

Requisitos: Linux con systemd (Debian 12 o posterior, o Ubuntu; la instalación usa `apt`),
Python 3.11 o posterior, root para instalar, unos 33 GB de disco libre para la precarga y
un televisor o un reproductor con receptor **Chromecast** integrado en la misma red. Las
mediciones se hicieron en una máquina con 8 GiB de memoria; con menos, simplemente hay
menos caché.

Desde el código fuente:

```sh
git clone https://github.com/anysda/torrcast && cd torrcast
sudo ./install.sh
```

La opción nombra el idioma a mano: `-en` instala la copia en inglés y `-ru` la rusa. Sin
opción, una instalación limpia escribe inglés.

La instalación encuentra el receptor sola, por mDNS y recorriendo las subredes locales. Si
hay varios, `cast --tv` muestra la lista y `cast --tv <ip>` escribe la dirección
directamente.

## Comandos

```text
cast <consulta> [sNeM]  # buscar y reproducir; sNeM es temporada y episodio: cast "doctor who" s2e5
cast                    # qué se está reproduciendo (igual que cast status)
cast stop               # cortar el cast y guardar la posición
cast status             # posición, archivo, pista, torrent, parte ya precargada
cast doctor             # revisa la terminal, ffmpeg, los servicios, el receptor y el torrent
cast log [--since 2d]   # diario de sesiones: cada rebuffer y cada corte
cast voices <consulta>  # las pistas de audio del release que irá al televisor
cast releases <consulta> # la tabla de releases, por película
cast -tg                # configuración del bot de Telegram
cast --tv               # buscar receptores en la red
cast -h                 # ayuda con todas las opciones
```

Opciones útiles: `--menu` (preguntar qué película), `--pick N`, `--release N`,
`--voice [N|ESTUDIO]`, `--new` (el mismo release desde el principio), `--dry` (todo el
análisis sin castear). Lo que quedó a medias continúa en silencio: el mismo torrent, el
mismo archivo, la misma pista y la posición guardada. La línea de reproducción lo dice y
nombra la salida.

## Bajo el capó

```text
consulta -> búsqueda (Prowlarr) -> análisis (nombres de release, sagas, sNeM)
        -> flujo (TorrServer) -> ffmpeg -> HLS -> cast (Chromecast)
                              \-> precarga (la película entera al disco, en segundo plano)
```

No hay ningún demonio de reproducción permanente: para cada reproducción `cast` levanta una
unidad transitoria de systemd con ffmpeg, un servidor HLS y un vigilante de la posición. El
comando puede terminar y la reproducción continúa. La precarga lee por delante a cuatro
veces el tiempo real bajo `nice` y se detiene por completo cuando la reproducción viva
necesita el procesador: el punto que se está viendo ahora mismo tiene siempre prioridad.

Los receptores están medidos y descritos con perfiles (Samsung Q70D y un reproductor
Android TV sobre Xiaomi TV Stick); un receptor desconocido recibe el perfil prudente. El
HEVC en un receptor sin decodificador propio se transcodifica entero, el 2160p se reproduce
reescalado a 1080p, y de eso siempre se avisa en voz alta.

El código se sostiene sobre reglas duras: arquitectura por capas (domain / ports / usecases
/ adapters / cli / runtime), más líneas de test que de código, un linter, mypy estricto y
puertas estructurales que deben pasar antes de cualquier release.

## Licencia y responsabilidad

El código de torrcast se distribuye bajo la licencia [MIT](../LICENSE). La licencia cubre
únicamente el código y no otorga ningún derecho sobre lo que veas con él: las fuentes y su
legalidad son responsabilidad del usuario.
