#!/bin/bash

mkdir -p ~/.config/autostart
cat <<EOF > ~/.config/autostart/cyberdeck.desktop
[Desktop Entry]
Type=Application
Name=Cyberdeck OS
Exec=/usr/bin/python3 /home/alana/cyberdeck/run.py
WorkingDirectory=/home/alana/cyberdeck
Terminal=false
EOF

echo "Autostart configured! Cyberdeck will start automatically on graphical desktop login."
