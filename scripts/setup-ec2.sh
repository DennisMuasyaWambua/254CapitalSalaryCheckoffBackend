#!/bin/bash
set -e

echo "🚀 Setting up EC2 for Salary Checkoff Backend Deployment"
echo "=========================================================="

# Update system
echo "📦 Updating system packages..."
sudo apt update && sudo apt upgrade -y

# Install Docker
echo "🐳 Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    rm get-docker.sh
    echo "✅ Docker installed"
else
    echo "✅ Docker already installed"
fi

# Install Docker Compose
echo "📦 Installing Docker Compose..."
if ! command -v docker-compose &> /dev/null; then
    sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
    echo "✅ Docker Compose installed"
else
    echo "✅ Docker Compose already installed"
fi

# Start Docker service
echo "🔄 Starting Docker service..."
sudo systemctl start docker
sudo systemctl enable docker

# Create application directory
echo "📁 Creating application directory..."
sudo mkdir -p /opt/salary_checkoff
sudo chown $USER:$USER /opt/salary_checkoff
cd /opt/salary_checkoff

# Create required directories
mkdir -p media logs staticfiles

# Create .env file template
if [ ! -f .env ]; then
    echo "📝 Creating .env template..."
    cat > .env << 'EOF'
# Django Settings
DJANGO_SETTINGS_MODULE=config.settings.production
SECRET_KEY=CHANGE_THIS_TO_A_SECURE_SECRET_KEY
DEBUG=False
ALLOWED_HOSTS=your-domain.com,your-ec2-ip

# Docker Settings
DOCKER_IMAGE=your-dockerhub-username/salary-checkoff-backend
DOCKER_TAG=latest

# Database
DB_USER=salary_checkoff_user
DB_PASSWORD=CHANGE_THIS_STRONG_PASSWORD
DATABASE_URL=postgresql://salary_checkoff_user:CHANGE_THIS_STRONG_PASSWORD@db:5432/salary_checkoff_db

# Redis
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/0
CELERY_RESULT_BACKEND=redis://redis:6379/0

# JWT Settings
JWT_ACCESS_TOKEN_LIFETIME_MINUTES=60
JWT_REFRESH_TOKEN_LIFETIME_DAYS=7

# AWS S3
USE_S3=True
AWS_ACCESS_KEY_ID=your-aws-access-key
AWS_SECRET_ACCESS_KEY=your-aws-secret-key
AWS_STORAGE_BUCKET_NAME=254capital-documents
AWS_S3_REGION_NAME=us-east-1

# Africa's Talking
AFRICASTALKING_USERNAME=your-username
AFRICASTALKING_API_KEY=your-api-key
AFRICASTALKING_SENDER_ID=254CAPITAL

# CORS
CORS_ALLOWED_ORIGINS=https://your-frontend-domain.com

# Email
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=True
EMAIL_HOST_USER=your-email@gmail.com
EMAIL_HOST_PASSWORD=your-app-password
DEFAULT_FROM_EMAIL=noreply@254capital.com

# OTP Settings
OTP_EXPIRY_SECONDS=300
OTP_MAX_ATTEMPTS=5

# Application URLs
FRONTEND_URL=https://your-frontend-domain.com
EOF
    echo "✅ .env template created at /opt/salary_checkoff/.env"
    echo "⚠️  IMPORTANT: Edit /opt/salary_checkoff/.env with your actual values!"
else
    echo "✅ .env file already exists"
fi

# Download docker-compose.yml from repository
echo "📥 Downloading docker-compose.yml..."
# This will be done by GitHub Actions, but we can create a placeholder
if [ ! -f docker-compose.yml ]; then
    echo "⚠️  docker-compose.yml will be pulled from GitHub during deployment"
fi

# Install Nginx
echo "🌐 Installing Nginx..."
if ! command -v nginx &> /dev/null; then
    sudo apt install nginx -y
    echo "✅ Nginx installed"
else
    echo "✅ Nginx already installed"
fi

# Configure Nginx
echo "⚙️  Configuring Nginx..."
sudo tee /etc/nginx/sites-available/salary_checkoff > /dev/null << 'EOF'
upstream salary_checkoff_app {
    server 127.0.0.1:8000 fail_timeout=0;
}

server {
    listen 80;
    server_name _;

    client_max_body_size 10M;

    location / {
        proxy_pass http://salary_checkoff_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_connect_timeout 120s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;

        proxy_redirect off;
    }

    location /static/ {
        alias /opt/salary_checkoff/staticfiles/;
        expires 30d;
        add_header Cache-Control "public, immutable";
    }

    location /media/ {
        alias /opt/salary_checkoff/media/;
        expires 7d;
        add_header Cache-Control "public";
    }
}
EOF

# Enable Nginx site
sudo ln -sf /etc/nginx/sites-available/salary_checkoff /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t
sudo systemctl restart nginx
sudo systemctl enable nginx

echo ""
echo "✅ EC2 Setup Complete!"
echo "=========================================================="
echo ""
echo "📋 Next Steps:"
echo "1. Edit /opt/salary_checkoff/.env with your actual configuration"
echo "2. Add GitHub secrets for CI/CD:"
echo "   - DOCKERHUB_USERNAME"
echo "   - DOCKERHUB_TOKEN"
echo "   - EC2_HOST (your EC2 public IP)"
echo "   - EC2_USERNAME (ubuntu)"
echo "   - EC2_SSH_KEY (your private SSH key)"
echo "3. Push your code to GitHub to trigger deployment"
echo "4. (Optional) Set up SSL with: sudo certbot --nginx -d your-domain.com"
echo ""
echo "🔑 Log out and log back in for Docker group changes to take effect"
echo "   Or run: newgrp docker"
echo ""
