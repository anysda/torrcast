[English](README.md) | [日本語](README-jp.md) | [Русский](README-ru.md)

# torrcast

> **Nota sobre el idioma.** El producto todavía no habla español: la interfaz, los mensajes y
> la selección de pista de audio existen solo en inglés y en ruso. El instalador de un solo
> comando pone la compilación **en inglés**, y esta página es únicamente una traducción de la
> documentación.

`cast` es una herramienta de línea de comandos que encuentra una película, una serie o un
anime por su nombre y lo reproduce en tu televisor, sin nube en la ruta de los datos y sin ir
pinchando torrents. El flujo va del enjambre a tu equipo y de ahí al televisor por la ruta por
la que el televisor te ve, sin ningún servidor de terceros de por medio.

La película se guarda en disco solo mientras la ves. Durante la reproducción, torrcast descarga
y, cuando hace falta, transcodifica la película entera en segundo plano. Una vez terminada la
precarga, el resto se reproduce sin acceso a internet, incluidos los saltos y sin pausas de
búfer. La caché se borra al terminar la reproducción. No hay biblioteca multimedia ni cola de
descargas: el disco contiene exactamente lo que se está reproduciendo, y solo mientras se
reproduce.

La idea es simple: **pides algo y empieza a reproducirse**. Un comando, una pregunta - a menudo
ninguna - y luego una imagen en la pantalla. Sin selección de release, sin cola de descargas y
sin tener que ordenar pistas de audio.

El segundo principio es **reproducción fluida por encima de la máxima nitidez**. La
reproducción no debe pararse a llenar el búfer. Si un release es demasiado pesado para el
receptor, torrcast lo transcodifica al vuelo y lo dice. La calidad se reduce solo como último
recurso y solo lo necesario.

No hay sustituciones silenciosas. Cada decisión automática recibe una línea honesta, por
ejemplo: `release 1 actually 574p - taking 2 (actually 1080p)`, `attention: ~36 Mbit/s -
heavy chunks get recoded on the fly`, o `video hevc - recoding it whole on the fly`.

## Instalación

```sh
curl -fsSL https://torrcast.anysda.space | sh
```

Una instalación limpia de Debian 12 **no** incluye `curl`; hay que instalarlo primero. El
bootstrap necesita `curl`, `tar`, `sha256sum` y `bash`. El comando de una línea le pregunta a
GitHub por la última versión, descarga ese tarball de release exacto, verifica su suma SHA-256
y ejecuta el `install.sh` que hay dentro. Cuando no se ejecuta como root, el bootstrap se
relanza a sí mismo a través de `sudo`; donde no hay `sudo`, se detiene e imprime el comando
exacto que hay que ejecutar como root.

El endpoint determina el idioma del producto que instala.
`https://torrcast.anysda.space` instala un `cast` en inglés: los menús, los mensajes y la pista
de audio que busca son todos en inglés. `https://rutorrcast.anysda.space` instala el mismo
release con el ruso como idioma del producto. En cualquier caso la elección no es definitiva:
`cast --en` y `cast --ru` cambian la copia instalada en cualquier momento.

Desde el código fuente:

```sh
git clone https://github.com/anysda/torrcast && cd torrcast
sudo ./install.sh
```

`sudo ./install.sh -en` y `sudo ./install.sh -ru` indican el idioma a mano: la opción fija
tanto la salida del propio instalador como el campo `language` de la configuración. Sin opción,
una instalación nueva guarda inglés, y una reinstalación conserva el idioma que ya está en la
configuración.

La instalación descubre receptores mediante mDNS y escaneando las subredes locales en el puerto
8009. Si hay un solo receptor, se guarda automáticamente. Si se encuentran varios, el instalador
lista sus nombres y direcciones y continúa sin elegir. Guarda una dirección directamente con
`cast --tv <ip>`, o usa `cast --tv` y elige un número.

La pantalla final del instalador habla del receptor en sí. El guardado se nombra por nombre y
dirección, o solo por dirección cuando el dispositivo no anunció ningún nombre, así como en una
reinstalación, donde la configuración solo contiene una dirección. De entre varios encontrados
lista tantos como quepan bajo la lista de comandos y cuenta el resto: "and 2 more". Una búsqueda
vacía no se queda en silencio: la pantalla dice que enciendas el televisor y nombra `cast --tv`;
en un terminal estrecho la redacción se acorta, pero el comando nunca desaparece de ella. Un
banco de pruebas simulado se nombra como tal: no emite a ninguna parte. Esa misma pantalla
nombra la puerta al otro idioma: `cast --ru` tras una instalación en inglés.

`install.sh` es idempotente: volver a ejecutarlo actualiza solo lo que cambió. No hace falta
registro ni claves de API externas: Prowlarr genera su propia clave de API, y la instalación la
lee y la guarda en la configuración de torrcast. Los indexadores que configura no necesitan
cuenta, ni captcha, ni clave: Knaben, RuTor, Nyaa.si y YTS se alcanzan directamente, y dos
pequeños adaptadores locales de solo lectura, instalados junto a torrcast y a la escucha solo en
localhost, añaden AniLibria (anime con pista de audio en ruso) y JacRed (un catálogo abierto de
releases y pistas de audio en ruso). Si un proveedor bloquea un indexador por su nombre, la
instalación monta un bypass local y dice si el nombre responde a través de él.

TorrServer y Prowlarr están fijados a versiones probadas con el resto del sistema. Ambas
fijaciones están en el bloque de ajustes al principio de `install.sh`. Si el release de Prowlarr
fijado ya no está en GitHub, la instalación lo dice y toma el más reciente en su lugar.
TorrServer nunca se sustituye: cuando falta su compilación fijada, se mantiene el binario ya
instalado y la instalación lo dice, y en una máquina que no lo tenga la instalación se detiene.

La fase de paquetes termina con una comprobación. El script compara cada archivo del paquete
instalado con las fuentes que están junto a `install.sh` e imprime una línea como `venv vs
repository check: N files match (sha256 ...)`. Una discrepancia nombra los archivos que difieren
y falla en lugar de informar de éxito.

El paquete vive en `/opt/torrcast/venv`; `/usr/local/bin/cast` es un enlace simbólico a
`/opt/torrcast/venv/bin/cast`.

## Requisitos

- Linux con systemd: Debian 12 o posterior, o Ubuntu con Python 3.11 o posterior disponible
  desde el gestor de paquetes del sistema. La instalación usa `apt`.
- Python 3.11 o posterior. `install.sh` toma el más reciente de `python3.13`, `python3.12`,
  `python3.11`; `TORRCAST_PYTHON` indica un intérprete a mano.
- `ffmpeg` 6.1 o posterior: `-readrate_initial_burst` es imprescindible. Si la versión del
  sistema es más antigua, está confinada en un snap o no supera una prueba rápida de MPEG-TS,
  `install.sh` coloca una compilación estática en `/usr/local/bin`.
- Privilegios de root para instalar unidades de systemd, paquetes y directorios bajo `/opt`,
  `/etc` y `/var/lib`.
- Memoria. Las mediciones se hacen en una máquina de 8 GiB; una más pequeña funciona con una
  caché más pequeña. La ventana de segmentos HLS en vivo se aloja en `/dev/shm`, junto a dos
  procesos de ffmpeg, así que cuando la caché de torrents va a memoria, la instalación resta
  1,75 GiB para el sistema, el reproductor y esos procesos antes de dimensionarla. Esa caché es
  lo que protege la reproducción de un corte de internet, y se coloca donde quepa más:
  normalmente en disco, o en memoria en una máquina con mucha RAM y poco disco. Su tamaño se
  calcula a partir de la máquina y se mantiene entre 256 MiB y 8 GiB; `TORRCAST_TS_CACHE` (en
  bytes) y `TORRCAST_TS_CACHE_DIR` sobrescriben el tamaño y el lugar.
- Unos 33 GB de disco libre: 30 GB para la precarga (`/var/lib/torrcast/warm`; `warm_dir` y
  `warm_budget_gb` en la configuración) y 3 GiB de espacio de partición que nunca se tocan.
  Cuando el disco lo permite, la instalación coloca ahí también hasta 8 GiB de caché de
  torrents; si no, reduce la caché o la traslada a memoria. El presupuesto de precarga lo
  comparten todos los títulos, y uno nuevo desaloja al que lleve más tiempo sin tocarse. Si el
  espacio se queda corto, la precarga se detiene con una línea explícita - `disk budget of 30 GB
  is used up`, o `the partition has N GB free - that's the last reserve` - mientras la
  reproducción continúa desde la ventana en vivo.
- Un televisor o decodificador con receptor **Chromecast** integrado en la misma red.

> **Nota sobre el receptor.** Hay dos perfiles de receptor medidos y distribuidos: `cautious
> (Samsung Q70D)` y `Android TV box (Xiaomi TV Stick)`. torrcast lee el pasaporte del receptor y
> elige uno de ellos; un receptor que no reconoce recibe el perfil cauteloso. Ese receptor puede
> funcionar, pero no está garantizado.

## Comandos

```text
cast <query> [sNeM] [--voice [N|STUDIO]] [--new] [--dry] [--pick N] [--menu] [--release N] [--file N]
cast                    # same as cast status
cast stop               # stop casting and save the position
cast status             # what plays, position/duration, file, track, stream, warmed share
cast doctor             # check terminal, locale, ffmpeg, services, receiver, and stream
cast log [--since WHEN] # sessions since 2d / 12h / 30m / YYYY-MM-DD
cast --tv               # find receivers; take a single one, or choose by number
cast --tv <ip>          # save an address directly
cast --en               # the whole product in English: text, bot replies and voice tracks
cast --ru               # the whole product in Russian
cast -tg                # open Telegram bot setup
cast -h, --help         # help with every public option
cast --version          # version
```

`sNeM` significa temporada N, episodio M, por ejemplo `s2e5`. Forma parte de la consulta
posicional, no es una opción. `2x5` es una forma aceptada de la misma petición.

El camino feliz no pregunta nada cuando torrcast está seguro. Las líneas de fase se redibujan en
el sitio en un terminal en vivo y se cierran con el tiempo que tardaron; la ejecución de abajo
está abreviada, porque los números de release, los tiempos y los recuentos de seeds varían con
las respuestas de los indexadores y del enjambre:

```text
$ cast matrix
searching “matrix”... 2.4 s
taking “The Matrix (1999)” - 3 pictures matched; another one: cast releases matrix and --pick N
...
packing... 3.1 s
waiting for the TV... 1.2 s
playing “The Matrix” (1999) · 1080p · eng - on TV   (start 9 s)
```

Tras la búsqueda, el comando nombra el título elegido y pasa directamente a la selección de
release. `--menu` pide un título de forma explícita. También aparece un menú por su cuenta
cuando no hay ninguna opción por defecto honesta, como cuando la parte de la franquicia
solicitada no está entre los resultados y cualquier elección reproduciría una película distinta:

```text
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
```

La lista es cronológica, y el número entre corchetes es lo que toma Enter: la **primera parte de
la franquicia cuyo propio enjambre está vivo**. Una franquicia se ve desde el principio, y las
partes con enjambres muertos se saltan. La línea justo encima de la pregunta deletrea esa
elección por su nombre, porque la opción por defecto a menudo no es la primera fila.

La valoración, la duración y una descripción de una frase llegan en segundo plano desde fuentes
abiertas y sin clave: Wikipedia, Wikidata y la exportación de valoraciones de IMDb que
`install.sh` deja en disco. El menú espera a la descripción, porque ocupa varias líneas y no se
pueden meter debajo de un elemento que alguien ya está leyendo. No espera a la valoración ni a
la duración: esas se escriben en el sitio, dentro de la línea ya impresa, y la línea cambia bajo
el cursor. La espera es un techo, no un retardo - 1,5 s, y 2,7 s en inglés, donde la descripción
cuesta una segunda tanda de consultas - y el menú aparece en cuanto llegan las descripciones, o
de inmediato cuando no hay nada que contar.

Los títulos que comparten nombre pero difieren en el año son películas distintas. Se toma la más
viva, porque la actividad del enjambre es la mejor pista de lo que se quería decir. Esto nunca
es silencioso: la línea nombra la película con su año, el número de seeds de su mejor release,
cuántas otras películas van bajo ese nombre y el comando `--menu` que las lista. Así,
`cast mummy` puede tomar la "Mummy" más viva y decirlo, mientras que `cast mummy --menu`
pregunta. Un número en la consulta se lee como una parte de la franquicia - o, en una serie,
como una temporada.

Donde no hay opción por defecto honesta, hay que responder al menú: Enter no toma nada y la
pregunta se repite hasta que se da un número. `cast matrix --pick 2` nombra el elemento por
adelantado y no pregunta nada; el número se comprueba contra el orden que se mostró, de modo que
un número que ahora corresponde a otra película se rechaza por su nombre en lugar de
reproducirse en silencio. Sin terminal - por SSH sin pty, desde cron - una pregunta se rechaza
en voz alta, y el rechazo nombra las dos salidas: el título exacto, o `--pick N`.

`start N s` en la línea de reproducción es el tiempo hasta el **primer fotograma en vivo en la
pantalla**, no hasta el momento en que empezó el empaquetado: el receptor informa de `PLAYING`
antes de mostrar imagen, y ese número sería halagador.

Un título sin terminar se reanuda en silencio, con el mismo release, archivo y pista, desde la
posición guardada. La línea de reproducción lo dice y termina con la forma de salir de ello:

```text
playing “Cyberpunk” · s1e2 · 1080p · track 1 · from 0:03:20 · pick another: --menu - on TV   (start 6 s)
```

`--new` reproduce el mismo release, archivo y pista desde el principio. `--menu`, `--pick N`,
`--release N` y `--file N` piden una película o un release propios y no los responde el
marcador. Un episodio explícito es una petición distinta: salta dentro del release guardado.

### Series

Nombra un episodio dentro de la consulta: `cast <series> s2e5` o `cast <series> 2x5`. No hay
menú de episodios: `cast <series>` reproduce el siguiente episodio del torrent registrado, y
tras `cast stop` se reanuda en la posición guardada.

Los episodios continúan solos. El siguiente archivo del mismo torrent arranca sin preguntar y
sin una nueva conexión con el receptor - la aplicación del receptor sigue en pie entre episodios
y solo se cierra cuando la serie termina. La unidad de reproducción nombra lo que viene:
`next episode: s2e6`.

Que se acabe una temporada no es el final de la serie. La unidad busca la siguiente temporada
por su cuenta, pidiendo el mismo título y el primer episodio de la siguiente temporada, y la
reproduce desde ahí:

```text
«Doctor Who» - season 2 watched, searching season 3
```

Si la siguiente temporada no está, la razón se dice en voz alta - `«Doctor Who» - season 2 was
the last: ...` - y la reproducción termina. Un `cast <series>` posterior sobre un torrent
agotado lo empieza de nuevo y lo dice: `“Doctor Who” - s2e13 was the last one in the release, so
playing from the start`.

### Pistas de audio

La selección de release es automática, y cada rechazo se nombra:

```text
release 2 does not fit (av1) - taking 5
```

Los receptores que no pueden decodificar HEVC reciben un transcodificado del flujo completo. Un
release marcado como HEVC entra en la cola solo como última esperanza - cuando ningún release
ordinario vivo lleva el episodio pedido - porque un transcodificado completo ocupa la CPU desde
el primer segundo hasta los créditos y arranca unos segundos más lento. Un release de 2160p se
reproduce igual, mediante un transcodificado completo escalado a 1080p; se toma cuando no hay
1080p, y nunca se impone a un 1080p vivo. Un release más pesado que el techo de bitrate no llega
siquiera a la cola. Un release con cero seeds cae por debajo de sus vecinos vivos, y cuando el
enjambre del elegido se queda callado, la selección baja por la cola dentro de su propio
presupuesto en lugar de rendirse en el primer release.

La selección de pista de audio también es automática, y sigue el idioma del producto. Una
instalación en inglés pone primero el audio en inglés, luego el idioma original de la propia
película, luego el ruso; la audiodescripción y los comentarios del equipo quedan los últimos.
Dentro de un nivel gana la pista más sencilla: un original por delante de un doblaje, y entre
las pistas rusas un doblaje por delante de la multivoz, la de dos voces y la de una sola voz.
`cast --ru` pone arriba la escalera rusa en su lugar. La línea de reproducción nombra la pista
elegida.

El mismo requisito llega a la selección de release. Con el inglés, un release cuyo pasaporte de
audio no confirme una pista en inglés se salta y la cola sigue adelante. Cuando ninguno de los
releases comprobados la tiene, torrcast reproduce el mejor de ellos y lo dice:

```text
no English voice in any of the checked releases (4) - turning on release 2, sound Japanese
```

Una pista de audio elegida explícitamente se recuerda para esa película, y un `cast` posterior
la reutiliza. La selección automática nunca escribe en esa memoria. Cuando la pista recordada
falta en un release nuevo, torrcast dice `no “eng · Original” voice track in this release -
taking the usual one` y conserva la memoria.

```text
cast voices <query>             # voice tracks of the release that would play
cast <query> --voice N          # take track N and remember it
cast <query> --voice STUDIO     # take a track by studio name or label, and remember it
cast <query> --voice            # numbered menu of tracks
```

`cast voices` imprime el release que tomaría y sus pistas numeradas, marcando la automática
`[default]` y la `[remembered]`. Un nombre dado a `--voice` se compara entero, ignorando
mayúsculas y espacios, y no como subcadena: `MVO` no coincide con `MVO (LostFilm)`.

### Registro de sesiones

torrcast guarda su propia traza de reproducción para investigar después de apagar el televisor:

```text
cast log                 # the last three sessions
cast log --since 2d      # everything since a boundary (2d / 12h / 30m / YYYY-MM-DD)
```

Sin `--since`, se muestran las tres últimas sesiones. Con él, el límite retrocede y el número de
sesiones no está acotado. Una sesión es una película o un episodio: cada episodio abre su propia
entrada, mientras que la búsqueda y la selección de release de una ejecución de `cast` quedan
bajo el identificador padre que esas entradas extienden, así que nada de una misma ejecución
queda disperso.

Una sesión muestra la consulta con el número de filas y de películas que trajo, el número de
resultados y el tiempo de cada indexador o su silencio, la cola con las razones por las que se
descartaron candidatos, el release tomado con su calidad, pista y bitrate, cada rebuffer, corte
de red, atasco y caída del receptor, los errores, y si se vio hasta el final o se detuvo en una
posición. Cada línea lleva su desplazamiento desde el inicio de la sesión.

La traza se guarda junto al estado como un archivo JSONL por día, se conserva siete días y está
limitada a 64 MiB en total, borrando primero lo más antiguo. No se sube nada. Las escrituras
pasan por una cola en segundo plano acotada, así que la reproducción nunca espera al disco;
cuando esa cola se desborda, el número de registros descartados va a la propia traza, de modo
que un hueco nunca es silencioso. Si no se ha reproducido nada durante una semana, `cast log`
imprime `no trace - not a single session over the week`.

### Controles de depuración

Estos controles exponen las tripas solo cuando se piden explícitamente:

```text
cast releases <query>              # table of releases per picture, then exit
cast <query> --release N           # use release N; numbers come from cast releases
cast <query> --release N --file N  # also take file N of that release
cast <query> --dry                 # the whole resolve without casting
cast <query> --new                 # the same release, file and track from the start
cast <query> --menu                # list the pictures and ask, instead of choosing
```

Un release o un archivo indicados a mano nunca se sustituyen: las puertas de selección no los
juzgan y la cola no contiene nada más. Pausa y salta con el mando del televisor. Los códigos de
salida son `0` para éxito, `1` cuando no se encontró nada, `2` para un fallo que torrcast no
pudo sortear (un servicio o el receptor), y `3` cuando la persona cancela una pregunta. `cast
doctor` devuelve `2` cuando falla alguna de sus comprobaciones.

## Cómo funciona

```text
query -> search (Prowlarr) -> parse (torrent names, franchises, sNeM)
      -> stream (TorrServer) -> ffmpeg -> HLS -> cast (Chromecast)
                            \-> warm (whole movie to disk, background)
```

No hay ningún demonio de reproducción permanente. Para cada reproducción, `cast` arranca una
unidad transitoria `torrcast-play` que sostiene ffmpeg, un servidor HLS y un vigilante de
posición. La dirección de servicio se deriva de la ruta hacia el televisor, así que al receptor
se le entrega una IP desnuda de la interfaz que realmente puede ver y el DNS nunca está en la
ruta de reproducción. El comando puede terminar mientras la reproducción continúa; los registros
de la unidad son `journalctl -u torrcast-play`, y `cast stop` detiene la unidad, que escribe la
posición al bajar. Los únicos servicios permanentes son TorrServer, Prowlarr, los adaptadores
locales de búsqueda de AniLibria y JacRed que Prowlarr consulta, y, para los trackers cuyo
nombre de host no sobrevive a la inspección SNI, un shim TLS local que fija solo los nombres que
lo necesitan.

La precarga espera a la primera imagen y luego lee por delante a cuatro veces el tiempo real
bajo `nice`. La cortesía por sí sola no libera un procesador, así que la precarga además se
congela del todo (`SIGSTOP`) cada vez que la reserva de la reproducción en vivo baja o el
codificador en vivo está trabajando: el punto que se está viendo ahora mismo siempre gana. La
rejilla de segmentos es determinista, así que el segmento `vN` es el mismo punto de la película
sin importar dónde empezó el empaquetado, y una pieza precargada y una pieza en vivo son
intercambiables bajo el mismo nombre. Saltar a una zona precargada no necesita red. Copiar o
transcodificar se decide pieza a pieza a partir del mapa de fotogramas clave, así que solo se
recodifican las piezas pesadas y las uniones entre piezas copiadas y recodificadas se mantienen
continuas en marcas de tiempo y en audio.

`cast status` informa de qué parte de la película está precargada y avisa cuando está precargada
entera. Si la fuente desaparece más allá de la zona precargada, la pantalla se queda a oscuras y
torrcast lo dice, en el journal y en `cast status`, con cuánto tiempo lleva a oscuras y cuándo
se rendirá. La paciencia del propio receptor se agota antes que eso, así que en cuanto se
confirma que la fuente ha vuelto torrcast recarga la reproducción en el segundo guardado. Solo
lo hace con un receptor libre y nunca interrumpe la reproducción de otra persona. Los intentos
están limitados por cada corte; cuando se agotan se queda a oscuras honestamente y el siguiente
`cast` se reanuda desde el punto guardado.

El progreso vive en `/var/lib/torrcast/state.json`, escrito de forma atómica; un marcador al 95
por ciento de la duración cuenta como visto. La pista de audio recordada es una etiqueta de
pista, no un número de pista, porque la siguiente ejecución puede elegir un release distinto en
el que esa misma pista lleve otro número. Si esa etiqueta no está en el release nuevo, torrcast
nombra la pista que suena en su lugar.

La configuración es `/etc/torrcast/config.json`, y solo la dirección del televisor es
obligatoria: el receptor y una clave de perfil opcional, las URL de Prowlarr y TorrServer, la
clave de API de Prowlarr, el transporte (`http` por defecto; `https` funciona pero quiere un
certificado en el que el televisor confíe), la dirección de servicio, el puerto y el directorio
de segmentos, la rejilla de segmentos y los ajustes de búfer, los umbrales de bitrate y de
transcodificación, y el interruptor, el directorio, el presupuesto de disco y la tasa de la
precarga.

Las propiedades medidas de cada receptor forman un perfil: el techo de peso de segmento, los
códecs que hay que transcodificar, los umbrales de bitrate, cuánto espera el receptor antes de
cortar la sesión, y los umbrales de atasco. El pasaporte del propio dispositivo (fabricante,
modelo, nombre) selecciona el perfil; un dispositivo que se queda callado o que no se reconoce
recibe el cauteloso. `cast doctor` nombra el perfil activo y de dónde salió, y `cast log` lleva
esa misma línea a cada resumen de sesión. `receiver_profile` fija un perfil por clave, y una
clave desconocida cae de vuelta al cauteloso. Un umbral escrito a mano en la configuración se
impone al perfil: el perfil solo rellena los valores que quedaron iguales al valor cauteloso por
defecto.

## Desarrollo

```sh
.venv/bin/ruff check
.venv/bin/ruff format --check
.venv/bin/mypy
.venv/bin/pytest
scripts/dead-code
```

Los cinco deben devolver el código 0. Ejecuta `mypy` sin argumentos: `[tool.mypy] files` en
`pyproject.toml` define su alcance (`torrcast`, `tgbot`, `tests`, `scripts`). Nombrar rutas en
la línea de comandos reduce ese alcance en silencio.

`scripts/dead-code` ejecuta cuatro etapas, y el alcance de cada una es su razón de ser. Los
nombres no llamados se buscan en el paquete junto con `scripts`, pero deliberadamente sin los
tests, de modo que el código cuyo único llamador es su propio test espejo se elimina junto con
ese test. La segunda etapa busca nombres que ningún test llama, la tercera módulos del paquete
que nadie importa, y la cuarta fixtures que ningún test pide. Los llamadores que ningún grafo de
imports puede ver se nombran explícitamente: los manejadores de peticiones de `http.server` en
`scripts/vulture-whitelist.py`, y los puntos de entrada de consola, `python -m`, las sondas de
`scripts/`, y los nombres que el instalador y las definiciones de indexadores mencionan como
cadenas, entre las raíces del grafo.

`scripts/test-gate` ejecuta todo eso más la puerta de estructura, los contratos de la CLI y del
instalador, los espejos de cableado, y los conjuntos de tests de máquina y de ffmpeg.

Las capas son `domain` (modelos y reglas puros), `ports` (contratos externos), `usecases`
(escenarios), `adapters` (el único sitio autorizado a tocar la red, el disco y los
subprocesos), `cli` y `runtime` (cableado). De las capas del paquete, solo `runtime` puede
importar `adapters`. `scripts/structure-gate` impone dieciséis reglas, entre ellas una clase o
función pública por módulo, un módulo con su nombre, un techo de 200 líneas, un test espejo para
cada módulo, y esa tabla de imports. Cada regla tiene una sonda negativa en
`tests/test_structure_gate.py`. `scripts/where.py` dice dónde está declarado un símbolo.

El directorio `scripts/` también contiene sondas para rejillas de segmentos y mapas de
fotogramas clave, benchmarks de arranque en frío y de transcodificación, comprobaciones de
trackers de torrents, recolección de pistas de audio, y pruebas de humo sobre receptores reales.
Una sonda recibe la ruta de su entrada en la línea de comandos, y cuando escribe una salida deja
un `<output>.passport.json` junto a ella: el commit, una huella calculada sobre los propios
archivos del paquete, el nombre de la sonda y su SHA-256, la marca de tiempo, la línea de
comandos, y el tamaño, el número de líneas y el SHA-256 de cada entrada y de la salida. El
commit puede faltar, porque el código se copia a máquinas que no tienen repositorio; la huella
nunca falta, y es lo que demuestra que dos ejecuciones usaron el mismo código.

El pasaporte también declara si la ejecución en sí fue válida, y lo dice explícitamente cuando
nadie midió eso, porque el silencio se leería como "válida". Una medición sobre un receptor real
la toman dos instrumentos, la traza propia de torrcast y el registro del propio receptor, y el
segundo puede pararse en silencio. Una ejecución cuyo registro del receptor se quedó ciego se
reporta como una medición estropeada y su recuento de atascos no se imprime en absoluto, en
lugar de colar un cero conseguido por un instrumento muerto. Un guardián acompañante,
`scripts/probesign.py`, comprueba que cada umbral de receptor del árbol nombre la sonda con la
que se midió.

## Licencia

[MIT](LICENSE). La licencia cubre el código propio de torrcast y no otorga derecho alguno sobre
nada de lo que se vea con él. Las fuentes y su legalidad son responsabilidad del usuario.
