#!/bin/bash

echo "Installing X11 server dependencies..."
sudo apt-get update
sudo apt-get install -y xserver-xorg xinit

# To allow non-root users to start X, we might need to adjust Xwrapper
echo "allowed_users=console" | sudo tee -a /etc/X11/Xwrapper.config

echo "Installing Cyberdeck OS Systemd Service..."
sudo cp cyberdeck.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable cyberdeck.service
sudo systemctl start cyberdeck.service

echo "Done! The service will now launch X11 and host Pygame."
echo "You can check the status with:"
echo "sudo systemctl status cyberdeck.service"
