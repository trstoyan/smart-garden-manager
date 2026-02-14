# Security Configuration

## Environment Variables

This project uses environment variables to manage sensitive configuration. Create a `.env` file in the project root with the following variables:

```bash
cp .env.example .env
```

### Required Environment Variables

- `SECRET_KEY`: Django secret key (generate a new one for production)
- `DEBUG`: Set to `False` for production
- `ALLOWED_HOSTS`: Comma-separated list of allowed hosts

### Security Checklist

Before deploying to production:

- [ ] Generate a new SECRET_KEY and set it in production environment
- [ ] Set DEBUG=False in production
- [ ] Configure proper ALLOWED_HOSTS
- [ ] Use HTTPS in production (SSL certificates)
- [ ] Configure database with proper authentication
- [ ] Set up proper logging
- [ ] Enable security middleware
- [ ] Configure CORS properly for your frontend

### Development vs Production

This settings file automatically configures security based on the DEBUG setting:

- **Development (DEBUG=True)**: Relaxed CORS, detailed error pages
- **Production (DEBUG=False)**: Strict security headers, HTTPS redirects, secure cookies

## Database Security

- SQLite is used for development
- For production, configure PostgreSQL with proper user credentials
- Never commit database files or credentials to version control

## API Security

- Authentication required for all API endpoints
- Session-based authentication for web interface
- Consider JWT tokens for mobile apps

## Device Security

When integrating IoT devices:

- Use secure MQTT with authentication
- Validate all sensor data inputs
- Implement device registration/authorization
- Monitor for unusual device behavior

## Regular Security Tasks

- Rotate SECRET_KEY periodically
- Update dependencies regularly
- Monitor access logs
- Backup database securely