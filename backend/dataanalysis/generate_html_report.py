"""
生成 HTML 可视化报告
"""

import json
from pathlib import Path
from datetime import datetime

OUTPUT_DIR = Path(__file__).parent / "output"
DATA_FILE = OUTPUT_DIR / "analysis_data.json"
HTML_FILE = OUTPUT_DIR / "analysis_report.html"

def load_data():
    """加载分析数据"""
    with open(DATA_FILE, 'r', encoding='utf-8') as f:
        return json.load(f)

def generate_html(data):
    """生成 HTML 报告"""
    user_stats = data['user_stats']
    chat_stats = data['chat_stats']
    tool_stats = data['tool_stats']
    generated_at = data['generated_at']
    
    html = f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MANHHH 项目数据分析报告</title>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}
        
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', 'Microsoft YaHei', sans-serif;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            padding: 20px;
            line-height: 1.6;
        }}
        
        .container {{
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            border-radius: 20px;
            box-shadow: 0 20px 60px rgba(0,0,0,0.3);
            overflow: hidden;
        }}
        
        .header {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 40px;
            text-align: center;
        }}
        
        .header h1 {{
            font-size: 36px;
            margin-bottom: 10px;
        }}
        
        .header .timestamp {{
            opacity: 0.9;
            font-size: 14px;
        }}
        
        .content {{
            padding: 40px;
        }}
        
        .section {{
            margin-bottom: 40px;
        }}
        
        .section h2 {{
            font-size: 24px;
            color: #333;
            margin-bottom: 20px;
            padding-bottom: 10px;
            border-bottom: 3px solid #667eea;
        }}
        
        .stats-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin-bottom: 30px;
        }}
        
        .stat-card {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 25px;
            border-radius: 15px;
            box-shadow: 0 4px 15px rgba(102, 126, 234, 0.3);
            transition: transform 0.3s ease;
        }}
        
        .stat-card:hover {{
            transform: translateY(-5px);
        }}
        
        .stat-card .label {{
            font-size: 14px;
            opacity: 0.9;
            margin-bottom: 10px;
        }}
        
        .stat-card .value {{
            font-size: 32px;
            font-weight: bold;
        }}
        
        .chart-container {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 10px;
            margin-bottom: 20px;
        }}
        
        .chart-container img {{
            width: 100%;
            border-radius: 10px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.1);
        }}
        
        .chart-title {{
            font-size: 18px;
            font-weight: bold;
            color: #333;
            margin-bottom: 15px;
            text-align: center;
        }}
        
        .top-users {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 10px;
        }}
        
        .top-users table {{
            width: 100%;
            border-collapse: collapse;
        }}
        
        .top-users th {{
            background: #667eea;
            color: white;
            padding: 12px;
            text-align: left;
        }}
        
        .top-users td {{
            padding: 12px;
            border-bottom: 1px solid #dee2e6;
        }}
        
        .top-users tr:hover {{
            background: #e9ecef;
        }}
        
        .footer {{
            background: #f8f9fa;
            padding: 20px;
            text-align: center;
            color: #666;
            font-size: 14px;
        }}
        
        @media (max-width: 768px) {{
            .stats-grid {{
                grid-template-columns: 1fr;
            }}
            
            .header h1 {{
                font-size: 28px;
            }}
            
            .content {{
                padding: 20px;
            }}
        }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 MANHHH 项目数据分析报告</h1>
            <p class="timestamp">生成时间: {generated_at}</p>
        </div>
        
        <div class="content">
            <!-- 用户统计 -->
            <div class="section">
                <h2>👥 用户统计</h2>
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="label">总用户数</div>
                        <div class="value">{user_stats['total_users']}</div>
                    </div>
                    <div class="stat-card">
                        <div class="label">有邮箱用户</div>
                        <div class="value">{user_stats['users_with_email']}</div>
                    </div>
                    <div class="stat-card">
                        <div class="label">配置 Tushare Token</div>
                        <div class="value">{user_stats['users_with_tushare']}</div>
                    </div>
                    <div class="stat-card">
                        <div class="label">启用 Tushare Token</div>
                        <div class="value">{user_stats['users_tushare_enabled']}</div>
                    </div>
                    <div class="stat-card">
                        <div class="label">最近7天新增</div>
                        <div class="value">{user_stats['new_users_7days']}</div>
                    </div>
                    <div class="stat-card">
                        <div class="label">最近30天新增</div>
                        <div class="value">{user_stats['new_users_30days']}</div>
                    </div>
                    <div class="stat-card">
                        <div class="label">平均积分</div>
                        <div class="value">{user_stats['credits_avg']}</div>
                    </div>
                    <div class="stat-card">
                        <div class="label">最高积分</div>
                        <div class="value">{user_stats['credits_max']}</div>
                    </div>
                </div>
                
                <div class="chart-container">
                    <div class="chart-title">用户增长趋势</div>
                    <img src="user_growth.png" alt="用户增长趋势">
                </div>
            </div>
            
            <!-- 聊天统计 -->
            <div class="section">
                <h2>💬 聊天统计</h2>
                <div class="stats-grid">
                    <div class="stat-card">
                        <div class="label">总会话数</div>
                        <div class="value">{chat_stats['total_sessions']}</div>
                    </div>
                    <div class="stat-card">
                        <div class="label">总对话数</div>
                        <div class="value">{chat_stats['total_conversations']}</div>
                    </div>
                    <div class="stat-card">
                        <div class="label">总消息数</div>
                        <div class="value">{chat_stats['total_messages']}</div>
                    </div>
                    <div class="stat-card">
                        <div class="label">人均消息数</div>
                        <div class="value">{chat_stats['avg_messages_per_user']}</div>
                    </div>
                    <div class="stat-card">
                        <div class="label">最近7天消息</div>
                        <div class="value">{chat_stats['messages_7days']}</div>
                    </div>
                    <div class="stat-card">
                        <div class="label">最近30天消息</div>
                        <div class="value">{chat_stats['messages_30days']}</div>
                    </div>
                </div>
                
                <div class="chart-container">
                    <div class="chart-title">聊天活跃度 (最近30天)</div>
                    <img src="chat_activity.png" alt="聊天活跃度">
                </div>
            </div>
            
            <!-- 最活跃用户 -->
            <div class="section">
                <h2>🏆 最活跃用户 TOP 10</h2>
                <div class="top-users">
                    <table>
                        <thead>
                            <tr>
                                <th>排名</th>
                                <th>用户名</th>
                                <th>消息数</th>
                            </tr>
                        </thead>
                        <tbody>
"""
    
    # 添加 TOP 用户
    for i, user in enumerate(chat_stats['top_users'], 1):
        html += f"""
                            <tr>
                                <td>#{i}</td>
                                <td>{user['username']}</td>
                                <td><strong>{user['message_count']}</strong> 条</td>
                            </tr>
"""
    
    html += """
                        </tbody>
                    </table>
                </div>
            </div>
            
            <!-- 词云和工具统计 -->
            <div class="section">
                <h2>☁️ 用户提问词云</h2>
                <div class="chart-container">
                    <img src="questions_wordcloud.png" alt="用户提问词云">
                </div>
            </div>
            
            <div class="section">
                <h2>🔧 工具使用统计</h2>
                <div class="chart-container">
                    <img src="tool_usage.png" alt="工具使用统计">
                </div>
            </div>
        </div>
        
        <div class="footer">
            <p>MANHHH 项目数据分析系统 | 自动生成于 """ + datetime.now().strftime('%Y-%m-%d %H:%M:%S') + """</p>
        </div>
    </div>
</body>
</html>
"""
    
    return html

def main():
    print("📝 生成 HTML 报告...")
    
    # 加载数据
    data = load_data()
    
    # 生成 HTML
    html = generate_html(data)
    
    # 保存文件
    with open(HTML_FILE, 'w', encoding='utf-8') as f:
        f.write(html)
    
    print(f"✅ HTML 报告已生成: {HTML_FILE}")
    print(f"🌐 在浏览器中打开即可查看完整的可视化报告")

if __name__ == '__main__':
    main()

