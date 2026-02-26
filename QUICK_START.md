# Quick Start Guide - Automated Deployment

Get your backend deployed to EC2 with Docker in 30 minutes.

## 🚀 Quick Steps

### 1. Create DockerHub Repository (2 min)
- Go to [hub.docker.com](https://hub.docker.com)
- Create account and repository: `your-username/salary-checkoff-backend`
- Generate Access Token: Settings → Security → New Access Token
- Save token securely

### 2. Launch EC2 Instance (5 min)
```
Instance Type: t3.medium
AMI: Ubuntu 22.04 LTS
Storage: 30GB GP3
Security Group:
  - Port 22 (SSH) - Your IP
  - Port 80 (HTTP) - 0.0.0.0/0
  - Port 443 (HTTPS) - 0.0.0.0/0
```

### 3. Set Up EC2 (5 min)
```bash
# Connect to EC2
ssh -i your-key.pem ubuntu@your-ec2-ip

# Download and run setup script
curl -o setup.sh https://raw.githubusercontent.com/your-org/salary_checkoff/main/scripts/setup-ec2.sh
chmod +x setup.sh
./setup.sh

# Log out and back in
exit
ssh -i your-key.pem ubuntu@your-ec2-ip
```

### 4. Configure Environment (5 min)
```bash
cd /opt/salary_checkoff
nano .env
```

Update these critical values:
```env
SECRET_KEY=your-generated-secret-key
DB_PASSWORD=strong-database-password
DOCKER_IMAGE=your-dockerhub-username/salary-checkoff-backend
ALLOWED_HOSTS=your-domain.com,your-ec2-ip
AWS_ACCESS_KEY_ID=your-aws-key
AWS_SECRET_ACCESS_KEY=your-aws-secret
```

Generate SECRET_KEY:
```bash
python3 -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

### 5. Upload docker-compose.yml (1 min)
```bash
# From your local machine
scp -i your-key.pem docker-compose.yml ubuntu@your-ec2-ip:/opt/salary_checkoff/
```

### 6. Configure GitHub Secrets (5 min)

Go to: GitHub Repo → Settings → Secrets and variables → Actions

Add:
- `DOCKERHUB_USERNAME`: your-dockerhub-username
- `DOCKERHUB_TOKEN`: your-dockerhub-token
- `EC2_HOST`: your-ec2-public-ip
- `EC2_USERNAME`: ubuntu
- `EC2_SSH_KEY`: contents of your-key.pem

### 7. Update Workflow File (2 min)

Edit `.github/workflows/deploy.yml`:
```yaml
env:
  DOCKER_IMAGE: your-dockerhub-username/salary-checkoff-backend  # ← Update this line
```

### 8. First Manual Deployment (3 min)
```bash
# On EC2
cd /opt/salary_checkoff
docker login
docker-compose up -d

# Wait for containers
sleep 20

# Run migrations
docker-compose exec web python manage.py migrate
docker-compose exec web python manage.py createsuperuser
docker-compose exec web python manage.py collectstatic --noinput

# Test
curl http://localhost:8000/api/v1/
```

### 9. Set Up SSL (2 min)
```bash
sudo apt install certbot python3-certbot-nginx -y
sudo certbot --nginx -d your-domain.com
```

### 10. Deploy from GitHub (1 min)
```bash
# From your local machine
git add .
git commit -m "Configure automated deployment"
git push origin main
```

Watch deployment at: GitHub → Actions tab

## ✅ Verify Deployment

```bash
# Check containers
docker-compose ps

# View logs
docker-compose logs web

# Test API
curl http://your-ec2-ip/api/v1/
curl https://your-domain.com/api/v1/

# Admin panel
https://your-domain.com/admin/

# API docs
https://your-domain.com/api/schema/swagger-ui/
```

## 🔄 Daily Usage

### Deploy New Changes
```bash
git push origin main  # Automatic deployment via GitHub Actions
```

### View Logs
```bash
ssh -i your-key.pem ubuntu@your-ec2-ip
cd /opt/salary_checkoff
docker-compose logs -f web
```

### Restart Services
```bash
docker-compose restart web
```

### Run Django Commands
```bash
docker-compose exec web python manage.py shell
docker-compose exec web python manage.py createsuperuser
```

### Backup Database
```bash
docker-compose exec db pg_dump -U salary_checkoff_user salary_checkoff_db > backup.sql
```

## 🆘 Troubleshooting

### Deployment fails
```bash
# Check GitHub Actions logs
# GitHub → Actions → Click on failed workflow

# Check EC2 logs
ssh -i your-key.pem ubuntu@your-ec2-ip
cd /opt/salary_checkoff
docker-compose logs web
```

### Can't connect to database
```bash
docker-compose ps  # Check if db container is running
docker-compose logs db
docker-compose restart db
```

### Container won't start
```bash
docker-compose down
docker-compose up -d
docker-compose logs
```

### Out of disk space
```bash
docker system prune -af
df -h
```

## 📚 Full Documentation

- [DEPLOYMENT.md](./DEPLOYMENT.md) - Complete deployment guide
- [docker-compose.yml](./docker-compose.yml) - Container configuration
- [.github/workflows/deploy.yml](./.github/workflows/deploy.yml) - CI/CD workflow

## 🔗 Useful Links

- **Application**: https://your-domain.com
- **Admin**: https://your-domain.com/admin/
- **API Docs**: https://your-domain.com/api/schema/swagger-ui/
- **DockerHub**: https://hub.docker.com/r/your-username/salary-checkoff-backend
- **GitHub Actions**: https://github.com/your-org/salary_checkoff/actions

## 💰 Monthly Costs (Estimate)

- EC2 t3.medium: ~$30-35
- S3 Storage (100GB): ~$2-3
- Data Transfer: ~$1-5
- **Total**: ~$35-45/month

## 🔐 Security Reminders

- ✅ Use strong passwords
- ✅ Keep SSH key secure
- ✅ Never commit .env files
- ✅ Enable MFA on AWS
- ✅ Regular backups
- ✅ Monitor logs
- ✅ Update dependencies

---

**Need help?** Check [DEPLOYMENT.md](./DEPLOYMENT.md) for detailed instructions.
