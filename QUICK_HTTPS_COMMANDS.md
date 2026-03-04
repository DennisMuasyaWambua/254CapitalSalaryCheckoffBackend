# Quick HTTPS Setup Commands

## On Your Local Machine

### 1. Configure DNS (Do this first!)
Go to your domain registrar and add:
- **Type:** A Record
- **Name:** api
- **Value:** 54.77.248.243

### 2. Upload files to EC2
```bash
cd /home/dennis/Desktop/docs/business/254capital/salary_checkoff/backend

scp nginx.conf setup-https.sh .env ec2-user@54.77.248.243:/opt/salary_checkoff/
```

## On EC2 Instance

### 3. SSH into server
```bash
ssh ec2-user@54.77.248.243
```

### 4. Run HTTPS setup script
```bash
cd /opt/salary_checkoff
sudo ./setup-https.sh
```

### 5. Restart Docker services
```bash
docker-compose down
docker-compose up -d
```

### 6. Test HTTPS
```bash
curl -I https://api.254-capital.com/api/v1/accounts/health/
```

## Update Frontend

Update your frontend environment variable:
```bash
# Change from:
API_URL=http://54.77.248.243

# To:
API_URL=https://api.254-capital.com
```

Then rebuild and redeploy your frontend.

## Troubleshooting Commands

```bash
# Check nginx status
sudo systemctl status nginx

# View nginx logs
sudo tail -f /var/log/nginx/api.254-capital.com.error.log

# Check Docker containers
docker-compose ps

# View Django logs
docker-compose logs -f web

# Check SSL certificate
sudo certbot certificates

# Test DNS
dig api.254-capital.com +short
```

## Expected Result

✅ Your API accessible at: `https://api.254-capital.com`
✅ HTTP automatically redirects to HTTPS
✅ No more mixed content errors
✅ Certificate auto-renews

---

**Need help?** Check `HTTPS_SETUP_GUIDE.md` for detailed instructions.
