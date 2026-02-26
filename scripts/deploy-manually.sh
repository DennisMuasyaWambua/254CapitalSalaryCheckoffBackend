#!/bin/bash
# Manual deployment script for EC2
# Use this if GitHub Actions fails or for manual deployments

set -e

echo "🚀 Manual Deployment Script"
echo "==========================="

# Configuration
APP_DIR="/opt/salary_checkoff"
DOCKER_IMAGE="${DOCKER_IMAGE:-your-dockerhub-username/salary-checkoff-backend}"
DOCKER_TAG="${DOCKER_TAG:-latest}"

# Check if running on EC2
if [ ! -d "$APP_DIR" ]; then
    echo "❌ Application directory not found: $APP_DIR"
    echo "Please run setup-ec2.sh first"
    exit 1
fi

cd $APP_DIR

# Check if .env exists
if [ ! -f .env ]; then
    echo "❌ .env file not found"
    echo "Please create .env file with production settings"
    exit 1
fi

# Load environment variables
set -a
source .env
set +a

echo "📦 Pulling latest Docker image..."
docker pull ${DOCKER_IMAGE}:${DOCKER_TAG}

echo "🛑 Stopping containers..."
docker-compose down

echo "🚀 Starting containers..."
docker-compose up -d

echo "⏳ Waiting for containers to be healthy..."
sleep 15

echo "📊 Running database migrations..."
docker-compose exec -T web python manage.py migrate --noinput

echo "📁 Collecting static files..."
docker-compose exec -T web python manage.py collectstatic --noinput

echo "🧹 Cleaning up old Docker images..."
docker image prune -af --filter "until=24h" || true

echo "📋 Container status:"
docker-compose ps

echo ""
echo "🏥 Running health check..."
if curl -f http://localhost:8000/api/v1/ > /dev/null 2>&1; then
    echo "✅ Deployment successful!"
    echo ""
    echo "📊 Application is running at:"
    echo "   - Local: http://localhost:8000"
    echo "   - Public: http://$(curl -s ifconfig.me)"
    echo ""
    echo "📝 Useful commands:"
    echo "   docker-compose logs -f web       # View logs"
    echo "   docker-compose ps                # Check status"
    echo "   docker-compose restart web       # Restart app"
else
    echo "❌ Health check failed!"
    echo ""
    echo "📋 Recent logs:"
    docker-compose logs --tail=50 web
    exit 1
fi
