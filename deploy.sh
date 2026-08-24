#!/bin/bash
if [ -z "$1" ]; then
    echo "Usage: ./deploy.sh <pi-ip>"
    exit 1
fi
PI_IP=$1
echo "Deploying to alana@$PI_IP..."
rsync -avz --exclude '.git' --exclude '__pycache__' --exclude 'deploy.sh' ./ alana@$PI_IP:~/cyberdeck/
echo "Restarting service on Pi..."
ssh alana@$PI_IP "sudo systemctl daemon-reload && sudo systemctl restart cyberdeck.service"
echo "Done!"
