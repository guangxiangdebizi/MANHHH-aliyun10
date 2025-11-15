"""
MANHHH 项目数据分析脚本
分析用户数、会话数、提问词云等
"""

import os
import sys
import sqlite3
import json
from datetime import datetime, timedelta
from pathlib import Path
from collections import Counter
import matplotlib.pyplot as plt
import matplotlib
import jieba
from wordcloud import WordCloud
import pandas as pd
import numpy as np

# 设置中文字体 - 稍后在下载字体后再配置
# matplotlib.rcParams['font.sans-serif'] = ['SimHei', 'DejaVu Sans', 'Arial Unicode MS']
# matplotlib.rcParams['axes.unicode_minus'] = False

# 项目路径
BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / "chat_history.db"
OUTPUT_DIR = Path(__file__).parent / "output"
OUTPUT_DIR.mkdir(exist_ok=True)

# 下载并设置中文字体（用于词云）
FONT_PATH = Path(__file__).parent / "SimHei.ttf"

def download_chinese_font():
    """下载中文字体用于词云和图表"""
    if FONT_PATH.exists():
        print(f"✓ 中文字体已存在: {FONT_PATH}")
        # 配置 matplotlib 使用下载的字体
        from matplotlib import font_manager
        font_manager.fontManager.addfont(str(FONT_PATH))
        matplotlib.rcParams['font.sans-serif'] = ['Source Han Sans SC', 'SimHei', 'DejaVu Sans']
        matplotlib.rcParams['axes.unicode_minus'] = False
        return str(FONT_PATH)
    
    print("⬇️ 下载中文字体...")
    import urllib.request
    
    # 使用开源字体：思源黑体
    font_url = "https://github.com/adobe-fonts/source-han-sans/raw/release/OTF/SimplifiedChinese/SourceHanSansSC-Regular.otf"
    
    try:
        urllib.request.urlretrieve(font_url, FONT_PATH)
        print(f"✓ 字体下载成功: {FONT_PATH}")
        # 配置 matplotlib 使用下载的字体
        from matplotlib import font_manager
        font_manager.fontManager.addfont(str(FONT_PATH))
        matplotlib.rcParams['font.sans-serif'] = ['Source Han Sans SC', 'SimHei', 'DejaVu Sans']
        matplotlib.rcParams['axes.unicode_minus'] = False
        return str(FONT_PATH)
    except Exception as e:
        print(f"⚠️ 字体下载失败: {e}")
        # 尝试使用系统字体
        system_fonts = [
            "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
            "/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf",
            "/System/Library/Fonts/PingFang.ttc",
            "C:\\Windows\\Fonts\\simhei.ttf"
        ]
        for font in system_fonts:
            if os.path.exists(font):
                print(f"✓ 使用系统字体: {font}")
                # 配置 matplotlib 使用系统字体
                from matplotlib import font_manager
                font_manager.fontManager.addfont(font)
                matplotlib.rcParams['font.sans-serif'] = ['WenQuanYi Zen Hei', 'SimHei', 'DejaVu Sans']
                matplotlib.rcParams['axes.unicode_minus'] = False
                return font
        
        print("⚠️ 未找到中文字体，词云可能无法正常显示中文")
        matplotlib.rcParams['axes.unicode_minus'] = False
        return None


def connect_db():
    """连接数据库"""
    if not DB_PATH.exists():
        print(f"❌ 数据库不存在: {DB_PATH}")
        sys.exit(1)
    
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def get_user_statistics(conn):
    """获取用户统计"""
    cursor = conn.cursor()
    
    stats = {}
    
    # 总用户数
    cursor.execute("SELECT COUNT(*) as count FROM users")
    stats['total_users'] = cursor.fetchone()['count']
    
    # 有邮箱的用户数
    cursor.execute("SELECT COUNT(*) as count FROM users WHERE email IS NOT NULL AND email != ''")
    stats['users_with_email'] = cursor.fetchone()['count']
    
    # 配置了 Tushare Token 的用户数
    cursor.execute("SELECT COUNT(*) as count FROM users WHERE tushare_token IS NOT NULL AND tushare_token != ''")
    stats['users_with_tushare'] = cursor.fetchone()['count']
    
    # 启用了 Tushare Token 的用户数
    cursor.execute("SELECT COUNT(*) as count FROM users WHERE tushare_token_enabled = 1")
    stats['users_tushare_enabled'] = cursor.fetchone()['count']
    
    # 积分统计
    cursor.execute("SELECT AVG(credits) as avg, MIN(credits) as min, MAX(credits) as max FROM users")
    row = cursor.fetchone()
    stats['credits_avg'] = round(row['avg'] or 0, 2)
    stats['credits_min'] = row['min'] or 0
    stats['credits_max'] = row['max'] or 0
    
    # 注册时间分布（最近7天、30天）
    cursor.execute("""
        SELECT 
            COUNT(*) as count,
            datetime(created_at, 'localtime') as create_time
        FROM users 
        WHERE created_at >= datetime('now', '-7 days')
    """)
    stats['new_users_7days'] = len(cursor.fetchall())
    
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM users 
        WHERE created_at >= datetime('now', '-30 days')
    """)
    stats['new_users_30days'] = cursor.fetchone()['count']
    
    return stats


def get_chat_statistics(conn):
    """获取聊天统计"""
    cursor = conn.cursor()
    
    stats = {}
    
    # 总会话数
    cursor.execute("SELECT COUNT(DISTINCT session_id) as count FROM chat_records")
    stats['total_sessions'] = cursor.fetchone()['count']
    
    # 总对话数
    cursor.execute("SELECT COUNT(DISTINCT session_id || '-' || conversation_id) as count FROM chat_records")
    stats['total_conversations'] = cursor.fetchone()['count']
    
    # 总消息数
    cursor.execute("SELECT COUNT(*) as count FROM chat_records")
    stats['total_messages'] = cursor.fetchone()['count']
    
    # 最近7天、30天的消息数
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM chat_records 
        WHERE created_at >= datetime('now', '-7 days')
    """)
    stats['messages_7days'] = cursor.fetchone()['count']
    
    cursor.execute("""
        SELECT COUNT(*) as count
        FROM chat_records 
        WHERE created_at >= datetime('now', '-30 days')
    """)
    stats['messages_30days'] = cursor.fetchone()['count']
    
    # 平均每个用户的消息数
    cursor.execute("""
        SELECT COUNT(*) * 1.0 / COUNT(DISTINCT username) as avg
        FROM chat_records
        WHERE username IS NOT NULL
    """)
    stats['avg_messages_per_user'] = round(cursor.fetchone()['avg'] or 0, 2)
    
    # 最活跃的用户 TOP 10
    cursor.execute("""
        SELECT username, COUNT(*) as message_count
        FROM chat_records
        WHERE username IS NOT NULL
        GROUP BY username
        ORDER BY message_count DESC
        LIMIT 10
    """)
    stats['top_users'] = [dict(row) for row in cursor.fetchall()]
    
    return stats


def get_tool_statistics(conn):
    """获取工具调用统计"""
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT mcp_tools_called
        FROM chat_records
        WHERE mcp_tools_called IS NOT NULL AND mcp_tools_called != '[]'
    """)
    
    tool_counter = Counter()
    
    for row in cursor.fetchall():
        try:
            tools = json.loads(row['mcp_tools_called'])
            for tool in tools:
                if isinstance(tool, dict):
                    tool_name = tool.get('name', 'unknown')
                    tool_counter[tool_name] += 1
        except:
            pass
    
    return dict(tool_counter.most_common(20))


def get_user_questions(conn):
    """获取所有用户提问"""
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT user_input
        FROM chat_records
        WHERE user_input IS NOT NULL AND user_input != ''
        ORDER BY created_at DESC
    """)
    
    questions = [row['user_input'] for row in cursor.fetchall()]
    return questions


def generate_wordcloud(text, output_path, title="词云"):
    """生成词云"""
    if not text or not text.strip():
        print(f"⚠️ 文本为空，跳过词云生成: {title}")
        return
    
    # 下载中文字体
    font_path = download_chinese_font()
    
    # 使用结巴分词
    words = jieba.cut(text)
    filtered_words = []
    
    # 停用词
    stop_words = set([
        '的', '了', '是', '我', '你', '在', '有', '和', '就', '不', '人',
        '都', '一', '一个', '上', '也', '很', '到', '说', '要', '去', '吗',
        '会', '能', '没', '看', '好', '自己', '这', '那', '什么', '为',
        '着', '下', '他', '她', '它', '们', '这个', '那个', '怎么', '可以',
        '吧', '啊', '呢', '哦', '嗯', '哈', '嘿', '呀', '吧', '么', '吗'
    ])
    
    for word in words:
        if len(word) > 1 and word not in stop_words and word.strip():
            filtered_words.append(word)
    
    text_for_cloud = ' '.join(filtered_words)
    
    if not text_for_cloud.strip():
        print(f"⚠️ 分词后文本为空，跳过词云生成: {title}")
        return
    
    # 生成词云
    try:
        wordcloud = WordCloud(
            width=1600,
            height=800,
            background_color='white',
            font_path=font_path,
            max_words=200,
            relative_scaling=0.5,
            colormap='viridis'
        ).generate(text_for_cloud)
        
        plt.figure(figsize=(16, 8))
        plt.imshow(wordcloud, interpolation='bilinear')
        plt.title(title, fontsize=20, pad=20)
        plt.axis('off')
        plt.tight_layout(pad=0)
        plt.savefig(output_path, dpi=300, bbox_inches='tight')
        plt.close()
        
        print(f"✓ 词云已生成: {output_path}")
    except Exception as e:
        print(f"❌ 词云生成失败: {e}")


def plot_user_growth(conn):
    """绘制用户增长趋势"""
    cursor = conn.cursor()
    
    cursor.execute("""
        SELECT DATE(created_at) as date, COUNT(*) as count
        FROM users
        GROUP BY DATE(created_at)
        ORDER BY date
    """)
    
    data = cursor.fetchall()
    
    if not data:
        print("⚠️ 没有用户数据")
        return
    
    dates = [row['date'] for row in data]
    counts = [row['count'] for row in data]
    cumulative = np.cumsum(counts)
    
    fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 10))
    
    # 每日新增
    ax1.bar(dates, counts, color='skyblue', alpha=0.7)
    ax1.set_title('每日新增用户', fontsize=14, pad=10)
    ax1.set_xlabel('日期')
    ax1.set_ylabel('新增用户数')
    ax1.grid(True, alpha=0.3)
    plt.setp(ax1.xaxis.get_majorticklabels(), rotation=45, ha='right')
    
    # 累计用户
    ax2.plot(dates, cumulative, marker='o', color='coral', linewidth=2)
    ax2.fill_between(range(len(dates)), cumulative, alpha=0.3, color='coral')
    ax2.set_title('累计用户增长', fontsize=14, pad=10)
    ax2.set_xlabel('日期')
    ax2.set_ylabel('累计用户数')
    ax2.grid(True, alpha=0.3)
    plt.setp(ax2.xaxis.get_majorticklabels(), rotation=45, ha='right')
    
    plt.tight_layout()
    output_path = OUTPUT_DIR / 'user_growth.png'
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"✓ 用户增长图已生成: {output_path}")


def plot_chat_activity(conn):
    """绘制聊天活跃度"""
    cursor = conn.cursor()
    
    # 按日期统计消息数
    cursor.execute("""
        SELECT DATE(created_at) as date, COUNT(*) as count
        FROM chat_records
        GROUP BY DATE(created_at)
        ORDER BY date DESC
        LIMIT 30
    """)
    
    data = cursor.fetchall()
    
    if not data:
        print("⚠️ 没有聊天数据")
        return
    
    data = list(reversed(data))  # 按时间正序
    dates = [row['date'] for row in data]
    counts = [row['count'] for row in data]
    
    plt.figure(figsize=(14, 6))
    plt.bar(dates, counts, color='mediumseagreen', alpha=0.7)
    plt.title('最近30天聊天活跃度', fontsize=14, pad=10)
    plt.xlabel('日期')
    plt.ylabel('消息数')
    plt.xticks(rotation=45, ha='right')
    plt.grid(True, alpha=0.3, axis='y')
    plt.tight_layout()
    
    output_path = OUTPUT_DIR / 'chat_activity.png'
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"✓ 聊天活跃度图已生成: {output_path}")


def plot_tool_usage(tool_stats):
    """绘制工具使用统计"""
    if not tool_stats:
        print("⚠️ 没有工具调用数据")
        return
    
    tools = list(tool_stats.keys())[:15]  # 取前15个
    counts = [tool_stats[t] for t in tools]
    
    plt.figure(figsize=(12, 8))
    bars = plt.barh(tools, counts, color='steelblue', alpha=0.7)
    
    # 添加数值标签
    for i, (bar, count) in enumerate(zip(bars, counts)):
        plt.text(count, i, f' {count}', va='center', fontsize=10)
    
    plt.title('工具调用次数统计 (TOP 15)', fontsize=14, pad=10)
    plt.xlabel('调用次数')
    plt.ylabel('工具名称')
    plt.gca().invert_yaxis()
    plt.grid(True, alpha=0.3, axis='x')
    plt.tight_layout()
    
    output_path = OUTPUT_DIR / 'tool_usage.png'
    plt.savefig(output_path, dpi=300, bbox_inches='tight')
    plt.close()
    
    print(f"✓ 工具使用统计图已生成: {output_path}")


def generate_report(user_stats, chat_stats, tool_stats):
    """生成文本报告"""
    report = []
    report.append("=" * 60)
    report.append("MANHHH 项目数据分析报告")
    report.append("=" * 60)
    report.append(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    report.append("")
    
    report.append("【用户统计】")
    report.append(f"  总用户数: {user_stats['total_users']}")
    report.append(f"  有邮箱用户: {user_stats['users_with_email']}")
    report.append(f"  配置了 Tushare Token: {user_stats['users_with_tushare']}")
    report.append(f"  启用了 Tushare Token: {user_stats['users_tushare_enabled']}")
    report.append(f"  最近7天新增: {user_stats['new_users_7days']}")
    report.append(f"  最近30天新增: {user_stats['new_users_30days']}")
    report.append(f"  积分平均值: {user_stats['credits_avg']}")
    report.append(f"  积分范围: {user_stats['credits_min']} - {user_stats['credits_max']}")
    report.append("")
    
    report.append("【聊天统计】")
    report.append(f"  总会话数: {chat_stats['total_sessions']}")
    report.append(f"  总对话数: {chat_stats['total_conversations']}")
    report.append(f"  总消息数: {chat_stats['total_messages']}")
    report.append(f"  最近7天消息: {chat_stats['messages_7days']}")
    report.append(f"  最近30天消息: {chat_stats['messages_30days']}")
    report.append(f"  人均消息数: {chat_stats['avg_messages_per_user']}")
    report.append("")
    
    report.append("【最活跃用户 TOP 10】")
    for i, user in enumerate(chat_stats['top_users'], 1):
        report.append(f"  {i}. {user['username']}: {user['message_count']} 条消息")
    report.append("")
    
    report.append("【工具调用统计 TOP 10】")
    for i, (tool, count) in enumerate(list(tool_stats.items())[:10], 1):
        report.append(f"  {i}. {tool}: {count} 次")
    report.append("")
    
    report.append("=" * 60)
    report.append("分析完成！")
    report.append("=" * 60)
    
    report_text = '\n'.join(report)
    
    # 保存报告
    output_path = OUTPUT_DIR / 'analysis_report.txt'
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(report_text)
    
    print(report_text)
    print(f"\n✓ 报告已保存: {output_path}")
    
    return report_text


def main():
    """主函数"""
    print("🚀 开始数据分析...")
    print(f"📊 数据库路径: {DB_PATH}")
    print(f"📁 输出目录: {OUTPUT_DIR}")
    print("")
    
    # 首先下载并配置中文字体
    print("🔤 配置中文字体...")
    download_chinese_font()
    
    # 连接数据库
    conn = connect_db()
    
    try:
        # 1. 用户统计
        print("📈 分析用户统计...")
        user_stats = get_user_statistics(conn)
        
        # 2. 聊天统计
        print("💬 分析聊天统计...")
        chat_stats = get_chat_statistics(conn)
        
        # 3. 工具统计
        print("🔧 分析工具使用...")
        tool_stats = get_tool_statistics(conn)
        
        # 4. 获取用户问题
        print("❓ 提取用户提问...")
        questions = get_user_questions(conn)
        all_questions_text = '\n'.join(questions)
        
        # 5. 生成词云（确保字体已配置）
        print("☁️ 生成词云...")
        generate_wordcloud(
            all_questions_text,
            OUTPUT_DIR / 'questions_wordcloud.png',
            '用户提问词云'
        )
        
        # 6. 绘制图表
        print("📊 绘制统计图表...")
        plot_user_growth(conn)
        plot_chat_activity(conn)
        plot_tool_usage(tool_stats)
        
        # 7. 生成报告
        print("📝 生成分析报告...")
        generate_report(user_stats, chat_stats, tool_stats)
        
        # 8. 保存原始数据为 JSON
        print("💾 保存原始数据...")
        data = {
            'user_stats': user_stats,
            'chat_stats': chat_stats,
            'tool_stats': tool_stats,
            'generated_at': datetime.now().isoformat()
        }
        
        json_path = OUTPUT_DIR / 'analysis_data.json'
        with open(json_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        print(f"✓ 原始数据已保存: {json_path}")
        
        print("\n" + "=" * 60)
        print("✅ 数据分析完成！")
        print(f"📁 所有结果已保存到: {OUTPUT_DIR}")
        print("=" * 60)
        
    finally:
        conn.close()


if __name__ == '__main__':
    main()

