#!/bin/sh
set -e

# Limpiar locks stale de ejecuciones anteriores (un restart conserva /tmp y
# sin esto Xvfb muere con "Server is already active for display 99").
rm -f /tmp/.X99-lock /tmp/.X99-unix/X99 /tmp/.X11-unix/X99 2>/dev/null || true

# Display virtual: Chromium corre "headed" (anti-deteccion intacto) sin pantalla real
Xvfb :99 -screen 0 "${XVFB_SCREEN:-1440x900x24}" -nolisten tcp &

# Esperar a que el socket de Xvfb exista antes de conectar clientes.
i=0
while [ ! -S /tmp/.X11-unix/X99 ] && [ "$i" -lt 40 ]; do
    sleep 0.5
    i=$((i + 1))
done

if [ "${VNC_ENABLED:-1}" = "1" ]; then
    # VNC directo (opcional, clientes nativos)
    x11vnc -display :99 -forever -shared -rfbport 5900 ${VNC_PASSWORD:+-passwd "$VNC_PASSWORD"} &
    # noVNC: escritorio en el navegador en http://<host>:6080/vnc.html
    websockify --web /usr/share/novnc 6080 localhost:5900 &
fi

exec "$@"
