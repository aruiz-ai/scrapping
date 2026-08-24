#!/bin/sh
set -e

# Display virtual: Chromium corre "headed" (anti-deteccion intacto) sin pantalla real
Xvfb :99 -screen 0 "${XVFB_SCREEN:-1440x900x24}" -nolisten tcp &
sleep 1

if [ "${VNC_ENABLED:-1}" = "1" ]; then
    # VNC directo (opcional, clientes nativos)
    x11vnc -display :99 -forever -shared -rfbport 5900 ${VNC_PASSWORD:+-passwd "$VNC_PASSWORD"} &
    # noVNC: escritorio en el navegador en http://<host>:6080/vnc.html
    websockify --web /usr/share/novnc 6080 localhost:5900 &
fi

exec "$@"
