#!/bin/bash

# Script to deploy BradBot
set -e

APP_DIR="/home/ubuntu/bradbot"
SERVICE_NAME="bradbot"

echo "Starting deployment..."

# Navigate to app directory
cd $APP_DIR

# Pull latest changes (GitHub Actions will handle this)
# git pull origin main

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating virtual environment..."
    python3.11 -m venv venv
fi

# Activate virtual environment and install dependencies
echo "Installing dependencies..."
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# Stop the service if it's running
if systemctl is-active --quiet $SERVICE_NAME; then
    echo "Stopping $SERVICE_NAME service..."
    sudo systemctl stop $SERVICE_NAME
fi

# Copy service file and reload systemd
echo "Setting up systemd service..."
sudo cp bradbot.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable $SERVICE_NAME

# Start the service
echo "Starting $SERVICE_NAME service..."
sudo systemctl start $SERVICE_NAME

# Check status
echo "Checking service status..."
sudo systemctl status $SERVICE_NAME --no-pager

echo "Deployment complete!"
