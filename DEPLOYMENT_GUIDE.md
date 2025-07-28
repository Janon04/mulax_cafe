# Mulax Cafe Deployment Guide

## Quick Start

### 1. Prerequisites
- Python 3.11 or higher
- pip (Python package manager)
- Git (optional, for version control)

### 2. Installation
```bash
# Navigate to the application directory
cd mulax_cafe

# Install required dependencies
pip install -r requirements.txt

# Or install individual packages if requirements.txt is missing:
pip install flask flask-sqlalchemy flask-login flask-bootstrap5 python-dotenv flask-migrate flask-limiter flask-moment flask-restx apscheduler flask-mail flask-admin flask-wtf
```

### 3. Configuration
1. Review and update the `.env` file with your settings:
   ```bash
   # Database (optional - defaults to SQLite)
   DATABASE_URL=sqlite:///mulax_cafe.db
   
   # Email settings (for notifications)
   MAIL_SERVER=smtp.gmail.com
   MAIL_PORT=587
   MAIL_USERNAME=your-email@gmail.com
   MAIL_PASSWORD=your-app-password
   
   # Security
   SECRET_KEY=your-secret-key-here
   ```

### 4. First Run
```bash
# Start the application
python run.py
```

The application will:
- Create the database automatically
- Set up default admin and manager users
- Start on `http://localhost:5055`

### 5. Default Login
- **Username**: `admin`
- **Password**: Check the console output for the auto-generated password
- **Important**: Change the default password immediately after first login

## Production Deployment

### 1. Environment Setup
```bash
# Set production environment
export FLASK_ENV=production

# Use a production WSGI server
pip install gunicorn
```

### 2. Database Configuration
For production, use PostgreSQL or MySQL instead of SQLite:
```bash
# PostgreSQL example
DATABASE_URL=postgresql://username:password@localhost/mulax_cafe

# MySQL example  
DATABASE_URL=mysql://username:password@localhost/mulax_cafe
```

### 3. Run with Gunicorn
```bash
# Basic production setup
gunicorn -w 4 -b 0.0.0.0:5055 run:app

# With more options
gunicorn -w 4 -b 0.0.0.0:5055 --timeout 120 --keep-alive 2 run:app
```

### 4. Reverse Proxy (Nginx)
Create an Nginx configuration:
```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location / {
        proxy_pass http://127.0.0.1:5055;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
    
    location /static {
        alias /path/to/mulax_cafe/app/static;
        expires 1y;
        add_header Cache-Control "public, immutable";
    }
}
```

### 5. SSL/HTTPS Setup
```bash
# Install Certbot
sudo apt install certbot python3-certbot-nginx

# Get SSL certificate
sudo certbot --nginx -d your-domain.com
```

## Docker Deployment

### 1. Create Dockerfile
```dockerfile
FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 5055

CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5055", "run:app"]
```

### 2. Build and Run
```bash
# Build image
docker build -t mulax-cafe .

# Run container
docker run -d -p 5055:5055 --name mulax-cafe-app mulax-cafe
```

### 3. Docker Compose
```yaml
version: '3.8'
services:
  app:
    build: .
    ports:
      - "5055:5055"
    environment:
      - FLASK_ENV=production
      - DATABASE_URL=postgresql://postgres:password@db:5432/mulax_cafe
    depends_on:
      - db
    volumes:
      - ./logs:/app/logs
      
  db:
    image: postgres:13
    environment:
      - POSTGRES_DB=mulax_cafe
      - POSTGRES_USER=postgres
      - POSTGRES_PASSWORD=password
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  postgres_data:
```

## Cloud Deployment

### Heroku
1. Create `Procfile`:
   ```
   web: gunicorn run:app
   ```

2. Deploy:
   ```bash
   heroku create your-app-name
   heroku addons:create heroku-postgresql:hobby-dev
   git push heroku main
   ```

### AWS EC2
1. Launch EC2 instance (Ubuntu 20.04+)
2. Install dependencies:
   ```bash
   sudo apt update
   sudo apt install python3.11 python3-pip nginx
   ```
3. Clone and setup application
4. Configure Nginx and SSL
5. Use systemd for process management

### DigitalOcean App Platform
1. Connect your Git repository
2. Configure build and run commands:
   - Build: `pip install -r requirements.txt`
   - Run: `gunicorn -w 4 -b 0.0.0.0:$PORT run:app`

## Monitoring and Maintenance

### 1. Logging
- Application logs: `logs/mulax_cafe.log`
- Access logs: Configure in your web server
- Error tracking: Consider Sentry integration

### 2. Database Backups
```bash
# SQLite backup
cp instance/mulax_cafe.db backups/mulax_cafe_$(date +%Y%m%d).db

# PostgreSQL backup
pg_dump mulax_cafe > backups/mulax_cafe_$(date +%Y%m%d).sql
```

### 3. Health Checks
Create a health check endpoint:
```python
@app.route('/health')
def health_check():
    return {'status': 'healthy', 'timestamp': datetime.utcnow().isoformat()}
```

### 4. Process Management (systemd)
Create `/etc/systemd/system/mulax-cafe.service`:
```ini
[Unit]
Description=Mulax Cafe Application
After=network.target

[Service]
User=ubuntu
WorkingDirectory=/home/ubuntu/mulax_cafe
Environment=PATH=/home/ubuntu/mulax_cafe/venv/bin
ExecStart=/home/ubuntu/mulax_cafe/venv/bin/gunicorn -w 4 -b 127.0.0.1:5055 run:app
Restart=always

[Install]
WantedBy=multi-user.target
```

Enable and start:
```bash
sudo systemctl enable mulax-cafe
sudo systemctl start mulax-cafe
```

## Security Checklist

### Application Security
- [ ] Change default passwords
- [ ] Use strong SECRET_KEY
- [ ] Enable HTTPS in production
- [ ] Configure CORS properly
- [ ] Validate all user inputs
- [ ] Use environment variables for secrets

### Server Security
- [ ] Keep system updated
- [ ] Configure firewall
- [ ] Use non-root user
- [ ] Disable unnecessary services
- [ ] Regular security audits

### Database Security
- [ ] Use strong database passwords
- [ ] Restrict database access
- [ ] Regular backups
- [ ] Encrypt sensitive data

## Troubleshooting

### Common Issues

1. **Port already in use**
   ```bash
   # Find process using port
   sudo lsof -i :5055
   # Kill process
   sudo kill -9 <PID>
   ```

2. **Database connection errors**
   - Check DATABASE_URL in .env
   - Verify database server is running
   - Check network connectivity

3. **Permission errors**
   ```bash
   # Fix file permissions
   chmod +x run.py
   chown -R ubuntu:ubuntu /path/to/mulax_cafe
   ```

4. **Import errors**
   ```bash
   # Reinstall dependencies
   pip install -r requirements.txt --force-reinstall
   ```

### Performance Issues
- Monitor CPU and memory usage
- Check database query performance
- Review application logs
- Consider scaling horizontally

## Support

### Getting Help
1. Check application logs first
2. Review this deployment guide
3. Check the IMPROVEMENTS.md file for technical details
4. Verify all environment variables are set correctly

### Maintenance Schedule
- **Daily**: Check application status and logs
- **Weekly**: Review performance metrics
- **Monthly**: Update dependencies and security patches
- **Quarterly**: Full system backup and disaster recovery test

## Scaling Considerations

### Horizontal Scaling
- Use load balancer (Nginx, HAProxy)
- Multiple application instances
- Shared database and session storage
- CDN for static assets

### Vertical Scaling
- Increase server resources
- Optimize database queries
- Enable caching (Redis)
- Use async processing for heavy tasks

This deployment guide should help you get the Mulax Cafe application running in various environments. Always test in a staging environment before deploying to production.

