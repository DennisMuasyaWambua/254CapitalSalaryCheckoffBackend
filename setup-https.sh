#!/bin/bash

# HTTPS Setup Script for 254 Capital Salary Check-Off API
# This script sets up nginx, Certbot, and SSL certificates for api.254-capital.com
# Run this script on your EC2 instance (54.77.248.243)

set -e  # Exit on error

echo "=========================================="
echo "254 Capital API - HTTPS Setup Script"
echo "=========================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check if running as root or with sudo
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}Please run this script with sudo${NC}"
    exit 1
fi

echo -e "${YELLOW}Step 1: Updating system packages...${NC}"
apt update

echo -e "${YELLOW}Step 2: Installing nginx...${NC}"
apt install -y nginx

echo -e "${YELLOW}Step 3: Installing Certbot...${NC}"
apt install -y certbot python3-certbot-nginx

echo -e "${YELLOW}Step 4: Creating certbot webroot directory...${NC}"
mkdir -p /var/www/certbot

echo -e "${YELLOW}Step 5: Copying nginx configuration...${NC}"
# Copy the nginx configuration file
cp nginx.conf /etc/nginx/sites-available/api.254-capital.com

# Create a temporary HTTP-only configuration for initial Certbot verification
cat > /etc/nginx/sites-available/api.254-capital.com.temp << 'EOF'
server {
    listen 80;
    listen [::]:80;
    server_name api.254-capital.com;

    location /.well-known/acme-challenge/ {
        root /var/www/certbot;
    }

    location / {
        proxy_pass http://localhost:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
EOF

# Enable the temporary site
ln -sf /etc/nginx/sites-available/api.254-capital.com.temp /etc/nginx/sites-enabled/api.254-capital.com

# Remove default site if it exists
rm -f /etc/nginx/sites-enabled/default

echo -e "${YELLOW}Step 6: Testing nginx configuration...${NC}"
nginx -t

echo -e "${YELLOW}Step 7: Restarting nginx...${NC}"
systemctl restart nginx
systemctl enable nginx

echo -e "${YELLOW}Step 8: Checking if DNS is configured...${NC}"
DOMAIN_IP=$(dig +short api.254-capital.com | tail -n1)
SERVER_IP=$(curl -s ifconfig.me)

if [ "$DOMAIN_IP" != "$SERVER_IP" ]; then
    echo -e "${RED}WARNING: DNS not properly configured!${NC}"
    echo "Domain resolves to: $DOMAIN_IP"
    echo "This server IP: $SERVER_IP"
    echo ""
    echo "Please ensure api.254-capital.com points to this server's IP address."
    echo "You can configure this in your domain registrar's DNS settings."
    echo ""
    read -p "Press Enter to continue anyway, or Ctrl+C to exit..."
fi

echo -e "${YELLOW}Step 9: Obtaining SSL certificate from Let's Encrypt...${NC}"
echo "This will request a certificate for api.254-capital.com"
echo ""

# Obtain certificate
certbot certonly --nginx \
    -d api.254-capital.com \
    --non-interactive \
    --agree-tos \
    --email admin@254-capital.com \
    --no-eff-email

if [ $? -eq 0 ]; then
    echo -e "${GREEN}Certificate obtained successfully!${NC}"

    echo -e "${YELLOW}Step 10: Updating nginx configuration with SSL...${NC}"
    # Now use the full configuration with SSL
    rm /etc/nginx/sites-enabled/api.254-capital.com
    ln -sf /etc/nginx/sites-available/api.254-capital.com /etc/nginx/sites-enabled/api.254-capital.com

    echo -e "${YELLOW}Step 11: Testing nginx configuration...${NC}"
    nginx -t

    echo -e "${YELLOW}Step 12: Restarting nginx...${NC}"
    systemctl restart nginx

    echo -e "${GREEN}✓ HTTPS setup completed successfully!${NC}"
    echo ""
    echo "Your API is now accessible at: https://api.254-capital.com"
    echo ""
    echo "Certificate will auto-renew. Certbot renewal service status:"
    systemctl status certbot.timer --no-pager

else
    echo -e "${RED}Failed to obtain SSL certificate${NC}"
    echo "Please check the error messages above and ensure:"
    echo "1. api.254-capital.com points to this server's IP address"
    echo "2. Port 80 is open in your security group"
    echo "3. nginx is running correctly"
    exit 1
fi

echo ""
echo -e "${YELLOW}Additional Notes:${NC}"
echo "- Certificate auto-renewal is configured via systemd timer"
echo "- nginx logs: /var/log/nginx/"
echo "- Certificate location: /etc/letsencrypt/live/api.254-capital.com/"
echo "- To manually renew: sudo certbot renew"
echo ""
echo -e "${GREEN}Setup complete!${NC}"
