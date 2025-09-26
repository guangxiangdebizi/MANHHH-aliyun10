#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
检查数据库时间戳与本地时间的时区差异
"""

import sqlite3
from datetime import datetime

def check_timezone():
    """检查数据库时区设置"""
    
    # 连接数据库
    con = sqlite3.connect('chat_history.db')
    cur = con.cursor()
    
    print("=" * 50)
    print("🕐 数据库时区检查")
    print("=" * 50)
    
    # 获取最新的聊天记录时间
    cur.execute('''
        SELECT user_timestamp, username, user_input 
        FROM chat_records 
        WHERE user_timestamp IS NOT NULL 
        ORDER BY user_timestamp DESC 
        LIMIT 1
    ''')
    
    result = cur.fetchone()
    if not result:
        print("❌ 未找到聊天记录")
        return
    
    db_timestamp_str, username, user_input = result
    
    # 解析数据库时间戳
    # 格式: 2025-09-21T13:20:51.931815
    db_time = datetime.fromisoformat(db_timestamp_str.replace('T', ' ').split('.')[0])
    
    # 当前本地时间
    local_time = datetime.now()
    
    # 计算时间差
    time_diff = local_time - db_time
    
    print(f"📊 最新聊天记录:")
    print(f"   用户: {username}")
    print(f"   内容: {user_input[:50]}{'...' if len(user_input) > 50 else ''}")
    print()
    print(f"🕐 时间对比:")
    print(f"   数据库时间: {db_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   当前本地时间: {local_time.strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"   时间差: {time_diff}")
    print()
    
    # 分析时区
    hours_diff = time_diff.total_seconds() / 3600
    
    if abs(hours_diff) < 1:
        print("✅ 时间基本同步，可能是同一时区")
    elif 7 <= hours_diff <= 9:
        print("⚠️  数据库时间比本地时间慢约8小时")
        print("   可能原因: 数据库存储的是UTC时间，而本地是东八区时间")
    elif -9 <= hours_diff <= -7:
        print("⚠️  数据库时间比本地时间快约8小时") 
        print("   可能原因: 数据库存储的是东八区时间，而服务器在UTC时区")
    else:
        print(f"❓ 时间差异较大: {hours_diff:.1f}小时")
        print("   建议检查服务器时区设置")
    
    print()
    print(f"🌏 时区分析:")
    print(f"   时间差小时数: {hours_diff:.2f}")
    
    if 7 <= hours_diff <= 9:
        print("   建议: 在热力图分析时，将数据库时间 +8 小时转换为东八区时间")
    elif -9 <= hours_diff <= -7:
        print("   建议: 在热力图分析时，将数据库时间 -8 小时转换为UTC时间")
    
    con.close()

if __name__ == "__main__":
    check_timezone()
