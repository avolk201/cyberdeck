#!/bin/bash

echo "Installing Cyberdeck OS Systemd Service..."
sudo cp cyberdeck.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable cyberdeck.service
sudo systemctl start cyberdeck.service

echo "Done! You can check the status with:"
echo "sudo systemctl status cyberdeck.service"
