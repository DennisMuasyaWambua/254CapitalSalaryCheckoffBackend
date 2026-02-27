#!/bin/bash

# EC2 Setup Script for Salary Checkoff Backend
# This script installs Docker, Docker Compose, and sets up the application directory

set -e

echo "========================================="
echo "EC2 Setup for Salary Checkoff Backend"
echo "========================================="
echo ""

# Check if running as root or with sudo
if [ "$EUID" -ne 0 ]; then
    echo "Please run this script with sudo"
    exit 1
fi

# Update system packages
echo "📦 Updating system packages..."
apt-get update
apt-get upgrade -y

# Install required packages
echo "📦 Installing required packages..."
apt-get install -y \
    ca-certificates \
    curl \
    gnupg \
    lsb-release \
    git \
    unzip

# Install Docker
echo "🐳 Installing Docker..."
if ! command -v docker &> /dev/null; then
    # Add Docker's official GPG key
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg

    # Add the repository to Apt sources
    echo \
      "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/ubuntu \
      $(. /etc/os-release && echo "$VERSION_CODENAME") stable" | \
      tee /etc/apt/sources.list.d/docker.list > /dev/null

    apt-get update
    apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin

    echo "✅ Docker installed successfully"
else
    echo "✅ Docker already installed"
fi

# Start and enable Docker
systemctl start docker
systemctl enable docker

# Install Docker Compose (standalone)
echo "🐳 Installing Docker Compose..."
if ! command -v docker-compose &> /dev/null; then
    curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    chmod +x /usr/local/bin/docker-compose
    echo "✅ Docker Compose installed successfully"
else
    echo "✅ Docker Compose already installed"
fi

# Create application directory
echo "📁 Creating application directory..."
mkdir -p /opt/salary_checkoff
cd /opt/salary_checkoff

# Create required subdirectories
mkdir -p logs media staticfiles

# Set permissions
echo "🔒 Setting permissions..."
chown -R ubuntu:ubuntu /opt/salary_checkoff

# Add ubuntu user to docker group
usermod -aG docker ubuntu

# Configure firewall (UFW)
echo "🔥 Configuring firewall..."
if command -v ufw &> /dev/null; then
    ufw allow 22/tcp
    ufw allow 80/tcp
    ufw allow 443/tcp
    ufw allow 8000/tcp
    ufw --force enable
    echo "✅ Firewall configured"
fi

# Install and configure Nginx (optional reverse proxy)
echo "🌐 Would you like to install Nginx as a reverse proxy? (y/n)"
read -r install_nginx
if [ "$install_nginx" = "y" ] || [ "$install_nginx" = "Y" ]; then
    apt-get install -y nginx

    # Create basic Nginx configuration
    cat > /etc/nginx/sites-available/salary-checkoff << 'EOF'
server {
    listen 80;
    server_name _;

    client_max_body_size 100M;

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_connect_timeout 300s;
        proxy_send_timeout 300s;
        proxy_read_timeout 300s;
    }

    location /static/ {
        alias /opt/salary_checkoff/staticfiles/;
    }

    location /media/ {
        alias /opt/salary_checkoff/media/;
    }
}
EOF

    # Enable the site
    ln -sf /etc/nginx/sites-available/salary-checkoff /etc/nginx/sites-enabled/
    rm -f /etc/nginx/sites-enabled/default

    # Test and reload Nginx
    nginx -t
    systemctl restart nginx
    systemctl enable nginx

    echo "✅ Nginx installed and configured"
fi

# Display Docker version
echo ""
echo "========================================="
echo "Installation Summary"
echo "========================================="
docker --version
docker-compose --version

echo ""
echo "✅ EC2 setup completed successfully!"
echo ""
echo "Next steps:"
echo "1. Copy your .env file to /opt/salary_checkoff/.env"
echo "2. Copy your docker-compose.yml to /opt/salary_checkoff/docker-compose.yml"
echo "3. Configure GitHub secrets in your repository"
echo "4. Push to main branch to trigger deployment"
echo ""
echo "Application directory: /opt/salary_checkoff"
echo ""
