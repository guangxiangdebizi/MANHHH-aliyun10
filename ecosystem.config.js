module.exports = {
  apps: [
    {
      name: 'manhhh-frontend',
      script: 'http-server',
      args: '/home/ec2-user/AIWebHere/MANHHH-aliyun10/frontend -p 5231 -c-1 --cors',
      interpreter: 'none',
      error_file: '/home/ec2-user/AIWebHere/logs/manhhh-frontend-error.log',
      out_file: '/home/ec2-user/AIWebHere/logs/manhhh-frontend-out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
      autorestart: true,
      watch: false
    },
    {
      name: 'manhhh-backend',
      script: '/home/ec2-user/AIWebHere/MANHHH-aliyun10/venv/bin/uvicorn',
      args: 'main:app --host 0.0.0.0 --port 5232',
      cwd: '/home/ec2-user/AIWebHere/MANHHH-aliyun10/backend',
      interpreter: 'none',
      error_file: '/home/ec2-user/AIWebHere/logs/manhhh-backend-error.log',
      out_file: '/home/ec2-user/AIWebHere/logs/manhhh-backend-out.log',
      log_date_format: 'YYYY-MM-DD HH:mm:ss Z',
      autorestart: true,
      max_restarts: 10,
      min_uptime: '10s',
      watch: false
    }
  ]
};
