#!/bin/bash


#dette er et start script som blir kjørt av kode som ligger i /etc/systemd/system som gjør at programmet starter når pien booter
sleep 1
unclutter -idle 0.1 &

if [ -e /dev/dri/card0 ]; then
  export SDL_VIDEODRIVER=KMSDRM
  else
    export SDL_VIDEODRIVER=dummy
    fi

    cd /home/pi/

    # Kill any old app.py instances first
    pkill -f app.py || true

    # Restart automatically if it exits
    while true; do
      echo "Starting app.py..."
        /usr/bin/python3 app.py
          echo "App exited. Restarting in 3 seconds..."
            sleep 3
            done

