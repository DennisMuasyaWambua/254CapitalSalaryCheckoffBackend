# Deployment Guide - EC2 with Docker & GitHub Actions

This guide walks you through deploying the Salary Checkoff Backend to AWS EC2 using Docker images from DockerHub with automated GitHub Actions CI/CD.

## Architecture Overview

```
GitHub Push → GitHub Actions → Build Docker Image → Push to DockerHub →
SSH to EC2 → Pull Image → Deploy with Docker Compose
```

**Services in Docker:**
- Django Web Application (Gunicorn)
- PostgreSQL Database
- Redis Cache/Broker
- Celery Worker
- Celery Beat Scheduler
- Nginx Reverse Proxy (on host)

---

## Prerequisites

### 1. DockerHub Account
- Create account at [hub.docker.com](https://hub.docker.com)
- Create repository: `your-username/salary-checkoff-backend`
- Generate Access Token: Account Settings → Security → New Access Token

### 2. AWS EC2 Instance
- **Instance Type:** t3.medium or larger
- **AMI:** Ubuntu 22.04 LTS
- **Storage:** 30GB+ GP3 SSD
- **Security Group:**
  - Port 22 (SSH) - Your IP
  - Port 80 (HTTP) - 0.0.0.0/0
  - Port 443 (HTTPS) - 0.0.0.0/0

### 3. Domain Name (Optional)
- Point DNS A record to EC2 public IP

---

## Step 1: Set Up EC2 Instance

### Connect to EC2

```bash
chmod 400 your-key.pem
ssh -i your-key.pem ubuntu@your-ec2-ip
```

### Run Setup Script

```bash
# Download setup script
curl -o setup-ec2.sh https://raw.githubusercontent.com/your-repo/salary_checkoff/main/scripts/setup-ec2.sh

# Make executable
chmod +x setup-ec2.sh

# Run setup
./setup-ec2.sh
```

**Or manually:**

```bash
# Install Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh
sudo usermod -aG docker $USER

# Install Docker Compose
sudo curl -L "https://github.com/docker/compose/releases/latest/download/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose

# Create app directory
sudo mkdir -p /opt/salary_checkoff
sudo chown ubuntu:ubuntu /opt/salary_checkoff
cd /opt/salary_checkoff

# Create directories
mkdir -p media logs staticfiles

# Log out and back in
exit
ssh -i your-key.pem ubuntu@your-ec2-ip
```

---

## Step 2: Configure Environment Variables

```bash
cd /opt/salary_checkoff
nano .env
```

Copy from `.env.production.example` and update:

```env
# CRITICAL: Update these values
SECRET_KEY=generate-a-strong-secret-key-here
DB_PASSWORD=strong-database-password
DOCKERHUB_USERNAME=your-dockerhub-username
DOCKER_IMAGE=your-dockerhub-username/salary-checkoff-backend

# Update with your actual values
ALLOWED_HOSTS=your-domain.com,your-ec2-ip
AWS_ACCESS_KEY_ID=your-aws-key
AWS_SECRET_ACCESS_KEY=your-aws-secret
CORS_ALLOWED_ORIGINS=https://your-frontend.com
```

**Generate SECRET_KEY:**
```bash
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

---

## Step 3: Upload docker-compose.yml

```bash
# From your local machine
scp -i your-key.pem docker-compose.yml ubuntu@your-ec2-ip:/opt/salary_checkoff/
```

---

## Step 4: Configure GitHub Secrets

Go to your GitHub repository → Settings → Secrets and variables → Actions → New repository secret

Add these secrets:

| Secret Name | Value | Description |
|------------|-------|-------------|
| `DOCKERHUB_USERNAME` | your-username | DockerHub username |
| `DOCKERHUB_TOKEN` | dckr_pat_xxx | DockerHub access token |
| `EC2_HOST` | 54.123.45.67 | EC2 public IP address |
| `EC2_USERNAME` | ubuntu | EC2 SSH username |
| `EC2_SSH_KEY` | -----BEGIN RSA PRIVATE KEY----- | Full private SSH key content |

**Get SSH Key:**
```bash
cat your-key.pem
# Copy entire output including BEGIN and END lines
```

---

## Step 5: Update GitHub Workflow

Edit `.github/workflows/deploy.yml`:

```yaml
env:
  DOCKER_IMAGE: your-dockerhub-username/salary-checkoff-backend  # Update this
```

---

## Step 6: Initial Manual Deployment

Before using GitHub Actions, do first deployment manually:

```bash
# On EC2
cd /opt/salary_checkoff

# Log in to DockerHub
docker login

# Pull image (or use locally built)
docker pull your-dockerhub-username/salary-checkoff-backend:latest

# Start services
docker-compose up -d

# Run migrations
docker-compose exec web python manage.py migrate

# Create superuser
docker-compose exec web python manage.py createsuperuser

# Collect static files
docker-compose exec web python manage.py collectstatic --noinput

# Check status
docker-compose ps
docker-compose logs web
```

**Verify deployment:**
```bash
curl http://localhost:8000/api/v1/
```

---

## Step 7: Set Up Nginx (Already done by script)

Nginx configuration at `/etc/nginx/sites-available/salary_checkoff`:

```nginx
upstream salary_checkoff_app {
    server 127.0.0.1:8000 fail_timeout=0;
}

server {
    listen 80;
    server_name your-domain.com;

    client_max_body_size 10M;

    location / {
        proxy_pass http://salary_checkoff_app;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }

    location /static/ {
        alias /opt/salary_checkoff/staticfiles/;
    }

    location /media/ {
        alias /opt/salary_checkoff/media/;
    }
}
```

Test and restart:
```bash
sudo nginx -t
sudo systemctl restart nginx
```

---

## Step 8: Set Up SSL (Let's Encrypt)

```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx -y

# Get certificate
sudo certbot --nginx -d your-domain.com -d www.your-domain.com

# Test auto-renewal
sudo certbot renew --dry-run
```

---

## Step 9: Deploy via GitHub Actions

Now you can deploy by pushing to GitHub:

```bash
# From your local machine
git add .
git commit -m "Set up automated deployment"
git push origin main
```

**GitHub Actions will:**
1. Build Docker image
2. Push to DockerHub
3. SSH to EC2
4. Pull latest image
5. Restart containers
6. Run migrations
7. Collect static files
8. Health check

**Monitor deployment:**
- GitHub → Actions tab
- Watch deployment progress
- Check for errors

---

## Management Commands

### View Logs

```bash
# All services
docker-compose logs

# Specific service
docker-compose logs web
docker-compose logs celery_worker

# Follow logs
docker-compose logs -f web
```

### Restart Services

```bash
# Restart all
docker-compose restart

# Restart specific service
docker-compose restart web
docker-compose restart celery_worker
```

### Execute Commands

```bash
# Django shell
docker-compose exec web python manage.py shell

# Create superuser
docker-compose exec web python manage.py createsuperuser

# Run migrations
docker-compose exec web python manage.py migrate

# Database shell
docker-compose exec web python manage.py dbshell

# PostgreSQL shell
docker-compose exec db psql -U salary_checkoff_user -d salary_checkoff_db
```

### Update Environment Variables

```bash
nano /opt/salary_checkoff/.env
docker-compose down
docker-compose up -d
```

### Database Backup

```bash
# Backup
docker-compose exec db pg_dump -U salary_checkoff_user salary_checkoff_db | gzip > backup_$(date +%Y%m%d).sql.gz

# Restore
gunzip < backup_20240101.sql.gz | docker-compose exec -T db psql -U salary_checkoff_user -d salary_checkoff_db
```

### Clean Up

```bash
# Remove stopped containers
docker-compose down

# Remove with volumes (⚠️ deletes database)
docker-compose down -v

# Remove old images
docker image prune -af
```

---

## Monitoring

### Check Service Health

```bash
# Container status
docker-compose ps

# Resource usage
docker stats

# Web app health
curl http://localhost:8000/api/v1/

# Database connections
docker-compose exec db psql -U salary_checkoff_user -d salary_checkoff_db -c "SELECT count(*) FROM pg_stat_activity;"
```

### System Resources

```bash
# Disk usage
df -h

# Docker disk usage
docker system df

# Memory
free -h

# CPU and processes
htop
```

---

## Troubleshooting

### Container won't start

```bash
# Check logs
docker-compose logs web

# Check configuration
docker-compose config

# Recreate containers
docker-compose down
docker-compose up -d
```

### Database connection errors

```bash
# Check database is running
docker-compose ps db

# Check database logs
docker-compose logs db

# Test connection
docker-compose exec web python manage.py dbshell
```

### Permission errors

```bash
# Fix ownership
sudo chown -R ubuntu:ubuntu /opt/salary_checkoff/media
sudo chown -R ubuntu:ubuntu /opt/salary_checkoff/logs
```

### Out of disk space

```bash
# Clean Docker
docker system prune -af --volumes

# Check disk usage
du -sh /opt/salary_checkoff/*
```

---

## Rollback

If deployment fails:

```bash
# View available images
docker images

# Use previous image
docker-compose down
docker pull your-dockerhub-username/salary-checkoff-backend:previous-tag
# Update docker-compose.yml or .env with previous tag
docker-compose up -d
```

---

## Security Checklist

- [ ] Strong SECRET_KEY set
- [ ] DEBUG=False in production
- [ ] Database password is strong
- [ ] SSH key-only authentication (no password)
- [ ] Security group restricts SSH to your IP
- [ ] SSL certificate installed
- [ ] S3 bucket is private
- [ ] Environment variables not committed to Git
- [ ] Regular backups scheduled
- [ ] Monitoring and alerts configured

---

## Cost Optimization

- Use reserved instances for 1-3 year commitment (up to 72% savings)
- Stop instance during off-hours if not 24/7
- Use CloudWatch alarms for resource monitoring
- Enable S3 lifecycle policies for old files
- Review and delete unused volumes/snapshots

---

## Support

For issues:
1. Check logs: `docker-compose logs`
2. Check GitHub Actions output
3. Verify .env configuration
4. Check AWS service status
5. Review Django logs: `/opt/salary_checkoff/logs/`

---

## Quick Reference

```bash
# Deploy (push to GitHub)
git push origin main

# View logs
docker-compose logs -f web

# Restart
docker-compose restart web

# Backup database
docker-compose exec db pg_dump -U salary_checkoff_user salary_checkoff_db > backup.sql

# Django shell
docker-compose exec web python manage.py shell

# Health check
curl http://localhost:8000/api/v1/
```
