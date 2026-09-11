#!/bin/bash
if [ -z "$1" ]; then
    echo "Usage: ./deploy.sh <pi-ip>"
    exit 1
fi
PI_IP=$1
echo "Deploying to alana@$PI_IP..."
rsync -avz \
    --exclude '.git' \
    --exclude '__pycache__' \
    --exclude '.pytest_cache' \
    --exclude 'tests' \
    --exclude '.DS_Store' \
    --exclude '.test_heartbeat' \
    --exclude '*.log' \
    --exclude 'deploy.sh' \
    ./ alana@$PI_IP:~/cyberdeck/
echo "Installing service file + restarting on Pi..."
ssh alana@$PI_IP "sudo cp ~/cyberdeck/cyberdeck.service /etc/systemd/system/cyberdeck.service && sudo systemctl daemon-reload && sudo systemctl restart cyberdeck.service"
echo "Done!"
