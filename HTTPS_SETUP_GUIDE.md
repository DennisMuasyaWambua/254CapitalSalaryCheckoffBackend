# HTTPS Setup Guide for 254 Capital API

This guide will help you set up HTTPS for your backend API at `api.254-capital.com`.

## Prerequisites

- EC2 instance running at 54.77.248.243
- Docker and Docker Compose installed
- Domain `api.254-capital.com` pointing to your server's IP
- Port 80 and 443 open in your EC2 security group

## Step 1: Configure DNS

Before starting, ensure your domain is properly configured:

1. Go to your domain registrar (e.g., Namecheap, GoDaddy, Cloudflare)
2. Add an A record:
   - **Name**: `api`
   - **Type**: `A`
   - **Value**: `54.77.248.243`
   - **TTL**: `300` (5 minutes)

3. Verify DNS propagation (may take a few minutes):
   ```bash
   dig api.254-capital.com +short
   # Should return: 54.77.248.243
   ```

## Step 2: Configure EC2 Security Group

Ensure your EC2 security group allows the following inbound rules:

| Type  | Protocol | Port Range | Source    | Description      |
|-------|----------|------------|-----------|------------------|
| HTTP  | TCP      | 80         | 0.0.0.0/0 | HTTP access      |
| HTTPS | TCP      | 443        | 0.0.0.0/0 | HTTPS access     |
| SSH   | TCP      | 22         | Your IP   | SSH access       |

## Step 3: Upload Files to EC2

Upload the necessary files to your EC2 instance:

```bash
# From your local machine
scp nginx.conf setup-https.sh ec2-user@54.77.248.243:/opt/salary_checkoff/
scp .env ec2-user@54.77.248.243:/opt/salary_checkoff/
```

## Step 4: Run the Setup Script

SSH into your EC2 instance and run the setup script:

```bash
# SSH into your server
ssh ec2-user@54.77.248.243

# Navigate to the project directory
cd /opt/salary_checkoff

# Make the script executable (if not already)
chmod +x setup-https.sh

# Run the setup script with sudo
sudo ./setup-https.sh
```

The script will:
1. ✅ Update system packages
2. ✅ Install nginx
3. ✅ Install Certbot
4. ✅ Configure nginx
5. ✅ Obtain SSL certificate from Let's Encrypt
6. ✅ Enable HTTPS

## Step 5: Restart Docker Services

After HTTPS is set up, restart your Docker services to apply the new .env settings:

```bash
cd /opt/salary_checkoff

# Pull the latest configuration
docker-compose pull

# Restart services
docker-compose down
docker-compose up -d

# Check logs
docker-compose logs -f web
```

## Step 6: Verify HTTPS is Working

Test your API endpoints:

```bash
# Test HTTPS endpoint
curl -I https://api.254-capital.com/api/v1/accounts/health/

# Should return: HTTP/2 200
```

Or open in browser:
- https://api.254-capital.com/api/v1/accounts/health/
- https://api.254-capital.com/admin/

## Step 7: Update Frontend Configuration

Now update your frontend to use the HTTPS API URL:

### If using environment variables:
```bash
# In your frontend .env file
REACT_APP_API_URL=https://api.254-capital.com
# or
NEXT_PUBLIC_API_URL=https://api.254-capital.com
# or
VITE_API_URL=https://api.254-capital.com
```

### If hardcoded:
Replace all instances of:
- `http://54.77.248.243` → `https://api.254-capital.com`

## Certificate Auto-Renewal

The SSL certificate will automatically renew via Certbot's systemd timer.

Check renewal status:
```bash
sudo systemctl status certbot.timer
```

Test renewal process (dry run):
```bash
sudo certbot renew --dry-run
```

## Troubleshooting

### Issue: DNS not resolving

**Solution:**
```bash
# Check DNS propagation
dig api.254-capital.com +short

# If not returning 54.77.248.243, wait for DNS propagation (up to 24 hours)
# or flush your DNS cache
```

### Issue: Certificate validation failed

**Problem:** Certbot can't verify domain ownership

**Solution:**
1. Ensure port 80 is open in security group
2. Ensure DNS points to correct IP
3. Check nginx is running: `sudo systemctl status nginx`
4. Check nginx logs: `sudo tail -f /var/log/nginx/error.log`

### Issue: Mixed Content errors persist

**Problem:** Frontend still making HTTP requests

**Solution:**
1. Clear browser cache (Ctrl+Shift+Delete)
2. Verify frontend environment variables are updated
3. Rebuild and redeploy frontend
4. Check browser console for the actual URL being called

### Issue: 502 Bad Gateway

**Problem:** Nginx can't connect to Django backend

**Solution:**
```bash
# Check if Docker containers are running
docker-compose ps

# Check Django logs
docker-compose logs web

# Restart services
docker-compose restart web
```

### Issue: CORS errors

**Problem:** Frontend domain not in ALLOWED_ORIGINS

**Solution:**
1. Check `.env` file has correct CORS_ALLOWED_ORIGINS
2. Restart Docker: `docker-compose restart web`
3. Verify in Django logs

## Monitoring

### Check nginx status:
```bash
sudo systemctl status nginx
```

### Check nginx logs:
```bash
sudo tail -f /var/log/nginx/api.254-capital.com.access.log
sudo tail -f /var/log/nginx/api.254-capital.com.error.log
```

### Check Django logs:
```bash
cd /opt/salary_checkoff
docker-compose logs -f web
```

### Check SSL certificate expiry:
```bash
sudo certbot certificates
```

## Security Best Practices

✅ **Enabled:**
- HTTPS redirect (HTTP → HTTPS)
- HSTS (Strict-Transport-Security)
- Secure cookies (SESSION_COOKIE_SECURE, CSRF_COOKIE_SECURE)
- XSS protection headers
- Content-Type protection

⚠️ **Review:**
- Regularly update nginx and system packages
- Monitor certificate expiry (auto-renews 30 days before)
- Review nginx access logs for suspicious activity

## URLs Summary

After setup, your API will be accessible at:

| Environment | URL                                | Protocol |
|-------------|---------------------------------------|----------|
| Production  | https://api.254-capital.com           | HTTPS    |
| Old URL     | ~~http://54.77.248.243~~ (redirects)  | HTTP     |

## Next Steps

1. ✅ Test all API endpoints with HTTPS
2. ✅ Update frontend to use `https://api.254-capital.com`
3. ✅ Test login flow from frontend
4. ✅ Monitor logs for any errors
5. ✅ Update documentation with new API URL

## Support

If you encounter issues:
1. Check the troubleshooting section above
2. Review nginx and Django logs
3. Verify DNS and security group settings
4. Test with `curl` to isolate frontend vs backend issues

## Files Created

- `nginx.conf` - Nginx configuration for HTTPS
- `setup-https.sh` - Automated HTTPS setup script
- `.env` - Updated with HTTPS settings
- `.env.production` - Production environment template

---

**Last Updated:** March 4, 2026
