# MCP Web Assistant - Frontend Configuration Guide

## Overview
This document explains how to configure the frontend of the MCP Web Assistant application.

## Configuration File: `config.json`

The frontend uses a `config.json` file located in the `frontend/` directory to specify backend connection settings.

### Configuration Structure

```json
{
  "backend": {
    "host": "localhost",
    "port": 8003,
    "protocol": "http",
    "wsProtocol": "ws"
  },
  "api": {
    "baseUrl": "",
    "wsUrl": ""
  }
}
```

### Configuration Fields

#### `backend` Section
- **`host`**: Backend server hostname (default: `localhost`)
- **`port`**: Backend server port (default: `8003`)  
- **`protocol`**: HTTP protocol (`http` or `https`)
- **`wsProtocol`**: WebSocket protocol (`ws` or `wss`)

#### `api` Section (Optional)
- **`baseUrl`**: Custom API base URL (overrides auto-generated URL)
- **`wsUrl`**: Custom WebSocket URL (overrides auto-generated URL)

### Environment-Specific Configurations

#### Development Environment
```json
{
  "backend": {
    "host": "localhost",
    "port": 8003,
    "protocol": "http",
    "wsProtocol": "ws"
  }
}
```

#### Production Environment
```json
{
  "backend": {
    "host": "your-domain.com",
    "port": 443,
    "protocol": "https", 
    "wsProtocol": "wss"
  }
}
```

### Medical Data Integration

Note: `msid` support has been removed. No URL parameter is required.

### Smart URL Generation

The frontend automatically generates backend URLs based on:

1. **Local Development**: Uses configured host and port
2. **Cross-Domain Deployment**: Uses current page domain with configured port
3. **Custom URLs**: Uses explicit `baseUrl` and `wsUrl` if provided

### Error Handling

If configuration loading fails:
- A user-friendly error message is displayed
- Reload button allows retry
- Console logs provide detailed error information

### File Structure

```
frontend/
├── config.json          # Main configuration file
├── index.html           # Main chat interface
├── tools.html           # Tools listing page
├── share.html           # Shared conversation viewer
├── css/
│   ├── style.css        # Main styles
│   └── tools.css        # Tools page styles
└── js/
    ├── config.js        # Configuration manager
    ├── chat.js          # Chat interface logic
    ├── ws.js            # WebSocket manager
    └── chat/
        ├── thinking-flow.js    # AI thinking display
        └── share-module.js     # Conversation sharing
```

### Troubleshooting

#### Connection Issues
1. Verify `config.json` exists and is valid JSON
2. Check backend server is running on specified port
3. Ensure no firewall blocking the connection
4. For HTTPS/WSS, verify SSL certificates

#### Medical Data Access
`msid` has been deprecated and removed from the system.

### Security Considerations

- Never expose sensitive credentials in `config.json`
- Use HTTPS/WSS in production environments
-- `msid` is deprecated and no longer used
- Implement proper CORS settings on backend

## Support

For configuration assistance:
- Check browser console for error messages
- Verify backend server logs
- Ensure all dependencies are installed
- Test with minimal configuration first
