#!/bin/bash

echo "Installing X11 server dependencies..."
sudo apt-get update
sudo apt-get install -y xserver-xorg xinit

# To allow non-root users and systemd to start X, adjust Xwrapper
echo "allowed_users=anybody" | sudo tee /etc/X11/Xwrapper.config > /dev/null
echo "needs_root_rights=yes" | sudo tee -a /etc/X11/Xwrapper.config > /dev/null

echo "Installing Cyberdeck OS Systemd Service..."
sudo cp cyberdeck.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable cyberdeck.service
sudo systemctl start cyberdeck.service

echo "Done! The service will now launch X11 and host Pygame."
echo "You can check the status with:"
echo "sudo systemctl status cyberdeck.service"
