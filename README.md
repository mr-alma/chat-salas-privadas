# Chat con salas privadas (Python + Flask)

Chat web con mensajes, archivos, audio, video, respuestas, reacciones e
indicadores de presencia. Cada conversación vive en una sala independiente que
puede ser pública, usar contraseña o usar un código de seis dígitos.

Dentro del chat hay una barra lateral de salas al estilo Discord. Recuerda
localmente las salas que ya se abrieron en ese dispositivo y permite cambiar
entre ellas usando la misma pestaña del navegador. El botón `+` abre la pantalla
para crear o buscar otra sala; las salas privadas nunca se publican en un
directorio global.

La interfaz responde al tamaño disponible: en PC utiliza toda la ventana con
una presentación amplia; en teléfono mantiene una composición compacta y
táctil. Ambos modos comparten el estilo degradado de la pantalla de creación,
animaciones suaves y compatibilidad con la preferencia del sistema para reducir
movimiento.

## Participantes y moderación

- Cada dispositivo conserva una identidad independiente dentro de la sala.
- Al crear una sala se puede activar la aprobación manual. El creador recibe
  las solicitudes y, al aceptarlas, asigna uno de cuatro roles.
- **Admin:** administra roles, elimina mensajes ajenos y expulsa a cualquier
  otra persona, incluso a otro Admin.
- **Moderador:** elimina mensajes ajenos y nunca puede cambiar roles ni expulsar
  a un Admin. La expulsión de un Participante o Invitado se convierte en una
  solicitud que debe aprobar obligatoriamente un Admin.
- **Participante:** puede enviar mensajes y multimedia y cambiar su nombre.
- **Invitado:** tiene acceso de solo lectura. La interfaz oculta por completo
  las herramientas de envío y muestra un aviso persistente.
- Los cambios de rol se aplican en tiempo real sin recargar la página. Los
  ascensos y descensos solo ofrecen destinos válidos según la jerarquía.
- Los roles aparecen como etiquetas junto al nombre en el chat, las menciones
  y la lista de personas conectadas.
- Todo borrado “para todos”, incluido el mensaje propio, conserva una auditoría
  privada del contenido original y deja un aviso gris con el autor del mensaje,
  la persona que lo borró y los roles de ambos.
- Las entradas y expulsiones aparecen como avisos de sistema centrados, sin
  utilizar una burbuja de mensaje normal.
- Los resultados de aprobación, rechazo y expulsión se muestran en avisos
  estilizados que pueden cerrarse.
- Cualquier participante puede fijar o desfijar un mensaje y consultarlo desde
  la cabecera.
- Al escribir `@` aparece una lista de participantes para completar menciones.
- Cada participante puede cambiar su nombre desde la cabecera. Los nombres son
  únicos dentro de la sala y el cambio se refleja en menciones y presencia.
- La barra lateral muestra cuántos mensajes hay sin leer en cada sala.

## Chats privados

- La barra lateral está dividida en **Salas** y **Privados**, con contadores de
  mensajes sin leer independientes.
- Al pulsar el nombre de otra persona, tanto en un mensaje como en la lista de
  usuarios online, aparecen las acciones **Mencionar** e **Iniciar chat
  privado**. Mencionar inserta directamente `@Nombre` en la caja de texto.
- Un chat privado nunca se abre sin consentimiento: la otra persona recibe una
  solicitud y puede aceptarla o rechazarla. Tras un rechazo se aplica un breve
  tiempo de espera antes de permitir otra solicitud.
- Cada conversación privada queda vinculada en el servidor a exactamente dos
  miembros. No existe una acción ni una ruta para invitar a una tercera
  persona, y los archivos también requieren pertenecer a uno de esos dos
  miembros.
- Los Invitados no pueden iniciar ni recibir chats privados, para conservar su
  restricción de solo lectura. Si uno de los dos miembros es expulsado o pasa a
  Invitado, el acceso al chat se revoca de inmediato.
- Los mensajes privados usan identificadores idempotentes para evitar
  duplicados y admiten texto, imágenes, videos, archivos y notas de voz
  grabadas directamente desde el navegador.
- Dentro del chat privado ambos se muestran como Participantes: los rangos de
  Admin y Moderador pertenecen únicamente a la sala y no dan autoridad sobre la
  conversación privada.
- Cada persona puede editar únicamente sus mensajes. Sus mensajes ofrecen
  **Borrar para mí** y **Borrar para todos**; los mensajes de la otra persona
  solo ofrecen **Borrar para mí**.
- Los mensajes admiten reacciones con emojis, un fijado compartido y destacados
  personales. El panel de la cabecera reúne el mensaje fijado y la lista de
  mensajes destacados; estos últimos aparecen con una estrella y un aura.
- La flecha de respuesta permite citar un mensaje privado concreto. La
  referencia se valida en el servidor y al pulsar la cita se vuelve al mensaje
  original.
- Los mensajes propios muestran los estados **enviado**, **entregado** y
  **visto** mediante marcas simples, dobles y dobles azules.

## Perfiles y búsqueda

- Al pulsar `Tú: Nombre` se abre el perfil personal, donde se puede cambiar la
  foto, el banner, el nombre único de la sala y una biografía de hasta 180
  caracteres.
- La foto de perfil y el banner pueden pulsarse para abrirse en un visor
  ampliado, tanto en perfiles propios como ajenos.
- Desde una sala, el menú de otra persona ofrece **Ver perfil**, **Mencionar** e
  **Iniciar chat privado**. Dentro de un chat privado solo ofrece
  **Ver perfil**.
- Los perfiles muestran foto, nombre, rol y biografía. En un chat privado el
  rol visible siempre es Participante, porque los rangos de sala no conceden
  permisos especiales en una conversación de dos personas.
- Los cambios de nombre, biografía, foto y banner se sincronizan en tiempo real
  en la sala y en todos los chats privados vinculados. También se actualizan los
  mensajes anteriores, las respuestas, los fijados, las búsquedas, las listas y
  cualquier perfil que permanezca abierto, sin recargar la página.
- La lupa de salas y privados busca únicamente dentro de la conversación
  actual. Las flechas recorren coincidencias y el contador indica la posición y
  el total.

## Contenido compartido

- Las salas y los chats privados tienen un botón `🗂️` en la cabecera para
  consultar todo el contenido enviado en esa conversación.
- El panel permite filtrar por fotos, videos, audios y archivos, muestra
  contadores por categoría y carga el historial por páginas.
- La vista previa antes de enviar limita imágenes y videos de gran resolución
  para que nunca tapen la caja de texto ni los controles en móvil o PC.
- Cada consulta se valida en el servidor y se limita a la sala o al chat
  privado actual. El contenido de otra sala o conversación nunca aparece en el
  panel.
- Las descargas conservan las mismas reglas de acceso que el chat: una persona
  ajena no puede abrir un archivo aunque conozca su enlace.

## Instalación

Requiere Python 3.9 o posterior.

```bash
python -m pip install -r requirements.txt
```

## Iniciar

En Windows:

```powershell
$env:USE_NGROK="0"
python app.py
```

Después abre `http://127.0.0.1:5000`.

## Desplegar en Northflank

El repositorio incluye un `Dockerfile` listo para desplegar sin ngrok.

1. Crea un servicio desde este repositorio y selecciona la construcción con
   Dockerfile.
2. Expón el puerto HTTP `8080`.
3. Añade un volumen persistente y móntalo en `/data`.
4. Configura la variable `CHAT_DATA_DIR=/data`.

La aplicación usa Gunicorn con un único proceso y varios hilos. Esto mantiene
consistentes la presencia, la escritura en tiempo real y SQLite. La base de
datos y los archivos subidos permanecen en el volumen, por lo que no se pierden
al volver a desplegar.

El contenedor ya configura `USE_NGROK=0`; Northflank entregará la dirección
pública HTTPS del servicio.

Para compartir el chat por internet, configura primero tu authtoken de ngrok y
ejecuta sin `USE_NGROK=0`:

```powershell
python -m pyngrok config add-authtoken TU_TOKEN
python app.py
```

## Salas y seguridad

- La pantalla inicial permite crear una sala pública, con contraseña o con
  código de seis dígitos.
- Las claves se procesan con `generate_password_hash` de Werkzeug y nunca se
  guardan en texto plano.
- La comprobación se hace en el servidor antes de permitir leer, escribir,
  reaccionar, ver presencia o descargar archivos.
- Tras una comprobación correcta, el navegador recibe un token aleatorio en una
  cookie `HttpOnly` y `SameSite=Lax`. En HTTPS también se marca `Secure`.
- Si se activa “Recordar este dispositivo”, la cookie dura 30 días; si no, se
  elimina al cerrar la sesión del navegador.
- En la base de datos solo se guarda el hash SHA-256 del token, no el token
  utilizable.
- Cinco intentos fallidos bloquean nuevos intentos desde esa dirección durante
  diez minutos.
- Los archivos nuevos se guardan fuera de la carpeta pública y pasan por la
  misma validación de acceso que los mensajes.
- La base de datos utiliza modo WAL para admitir lecturas y escrituras
  concurrentes de varios participantes sin bloquear el chat.
- Cada envío tiene un identificador único: los fallos transitorios se
  reintentan automáticamente sin crear mensajes duplicados. Si todos los
  reintentos fallan, el texto permanece en la caja para volver a enviarlo.

Al actualizar desde la versión anterior, la base de datos se migra sin borrar el
historial. Los mensajes existentes quedan en `/room/general`.

## Pruebas

```bash
python -m unittest discover -s tests -v
```

Las pruebas cubren creación de salas públicas y privadas, validación y hash de
claves, cookies de sesión y persistentes, límite de intentos, aislamiento entre
salas, descarga protegida de archivos, aprobación, rechazo, expulsión, permisos
por jerarquía, los cuatro roles, modo de solo lectura, cambios de rango,
auditoría privada del borrado moderado, nombres únicos, cambio de nombre,
mensajes de sistema, fijado, conteos sin leer, reintentos idempotentes y envíos
concurrentes de varios participantes. También cubren solicitud, aceptación,
rechazo, espera entre solicitudes, aislamiento estricto de chats privados,
descargas privadas, revocación por rol, galerías multimedia aisladas y
reintentos sin duplicados. También verifican edición y borrado privado,
reacciones, fijados, destacados personales, recibos de entrega y lectura,
perfiles protegidos, búsquedas aisladas y sincronización completa de perfiles
entre salas y chats privados.

## Datos

- La información se guarda en `chat.db`.
- Los archivos nuevos se guardan en `uploads/<sala>/`.
- El límite por archivo es 50 MB.
- `Ctrl + C` detiene el servidor.
