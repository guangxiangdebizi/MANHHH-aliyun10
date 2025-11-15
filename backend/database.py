# database.py
"""
SQLite数据库管理
存储聊天记录：用户问题、MCP工具返回内容、AI回复
"""

import os
import json
import uuid
import aiosqlite
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from pathlib import Path


class ChatDatabase:
    """聊天记录数据库管理类"""
    
    def __init__(self, db_path: str = "chat_history.db"):
        """初始化数据库连接
        
        Args:
            db_path: 数据库文件路径，默认为当前目录下的chat_history.db
        """
        # 确保使用绝对路径
        if not os.path.isabs(db_path):
            db_path = Path(__file__).parent / db_path
        
        self.db_path = str(db_path)
        print(f"📁 数据库路径: {self.db_path}")
    
    async def initialize(self):
        """初始化数据库表结构"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # 用户表
                DEFAULT_INITIAL_CREDITS = int(os.getenv("CREDITS_DEFAULT", "50"))
                await db.execute(f"""
                    CREATE TABLE IF NOT EXISTS users (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        username TEXT UNIQUE NOT NULL,
                        email TEXT,
                        password_hash TEXT NOT NULL,
                        credits INTEGER DEFAULT {DEFAULT_INITIAL_CREDITS},
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                # 兼容旧库：尝试补充 users.email 列
                try:
                    await db.execute("ALTER TABLE users ADD COLUMN email TEXT")
                except Exception:
                    pass
                # 兼容旧库：尝试补充 users.credits 列并设置默认值
                try:
                    await db.execute(f"ALTER TABLE users ADD COLUMN credits INTEGER DEFAULT {DEFAULT_INITIAL_CREDITS}")
                except Exception:
                    pass
                # 兼容旧库：尝试补充 users.tushare_token 列
                try:
                    await db.execute("ALTER TABLE users ADD COLUMN tushare_token TEXT")
                except Exception:
                    pass
                # 兼容旧库：尝试补充 users.tushare_token_enabled 列（默认关闭）
                try:
                    await db.execute("ALTER TABLE users ADD COLUMN tushare_token_enabled INTEGER DEFAULT 0")
                except Exception:
                    pass
                # 为 email 创建唯一索引（允许多个 NULL，但非 NULL 唯一）
                try:
                    await db.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_users_email_unique ON users(email)")
                except Exception:
                    pass

                # 创建聊天会话表
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS chat_sessions (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                # 创建聊天记录表
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS chat_records (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        session_id TEXT DEFAULT 'default',
                        conversation_id INTEGER,
                        user_id INTEGER,
                        username TEXT,
                        attachments TEXT, -- JSON 数组，保存用户随消息上传的附件元信息
                        usage TEXT, -- JSON，记录本轮模型token用量（input/output/total）
                        
                        -- 用户输入
                        user_input TEXT,
                        user_timestamp TIMESTAMP,
                        
                        -- MCP工具相关
                        mcp_tools_called TEXT,  -- JSON格式存储调用的工具信息
                        mcp_results TEXT,       -- JSON格式存储工具返回结果
                        
                        -- AI回复
                        ai_response TEXT,
                        ai_timestamp TIMESTAMP,
                        
                        -- 元数据
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        
                        FOREIGN KEY (session_id) REFERENCES chat_sessions(session_id)
                    )
                """)
                # 邮箱验证码表
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS email_verification_codes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        email TEXT NOT NULL,
                        code TEXT NOT NULL,
                        purpose TEXT NOT NULL,
                        expires_at TIMESTAMP NOT NULL,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        used INTEGER DEFAULT 0
                    )
                """)
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_email_codes_email_purpose 
                    ON email_verification_codes(email, purpose)
                """)
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_email_codes_created 
                    ON email_verification_codes(created_at)
                """)
                # 兼容旧库：已移除 msid 相关新增逻辑
                # 兼容旧库：补充 username / user_id 列
                try:
                    await db.execute("ALTER TABLE chat_records ADD COLUMN username TEXT")
                except Exception:
                    pass
                try:
                    await db.execute("ALTER TABLE chat_records ADD COLUMN user_id INTEGER")
                except Exception:
                    pass
                # 兼容旧库：尝试补充 attachments 列
                try:
                    await db.execute("ALTER TABLE chat_records ADD COLUMN attachments TEXT")
                except Exception:
                    pass
                # 兼容旧库：尝试补充 usage 列
                try:
                    await db.execute("ALTER TABLE chat_records ADD COLUMN usage TEXT")
                except Exception:
                    pass
                
                # 创建索引以提高查询性能
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_chat_records_session 
                    ON chat_records(session_id)
                """)
                # 已移除 msid 索引
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_chat_records_username 
                    ON chat_records(username)
                """)
                
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_chat_records_conversation 
                    ON chat_records(conversation_id)
                """)
                
                await db.execute("""
                    CREATE INDEX IF NOT EXISTS idx_chat_records_created 
                    ON chat_records(created_at)
                """)
                # 分享快照表：存储不可变只读快照，按 share_id 取回
                await db.execute("""
                    CREATE TABLE IF NOT EXISTS shared_snapshots (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        share_id TEXT UNIQUE NOT NULL,
                        data TEXT NOT NULL, -- JSON: 聊天记录数组
                        created_by_user_id INTEGER,
                        created_by_username TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    )
                """)
                
                await db.commit()
                print("✅ 数据库表结构初始化完成")
                return True
                
        except Exception as e:
            print(f"❌ 数据库初始化失败: {e}")
            return False

    async def create_user(self, username: str, email: str, password_hash: str) -> bool:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "INSERT INTO users (username, email, password_hash) VALUES (?, ?, ?)",
                    (username, email, password_hash)
                )
                await db.commit()
                return True
        except Exception as e:
            print(f"❌ 创建用户失败: {e}")
            return False

    async def get_user_by_username(self, username: str) -> Optional[Dict[str, Any]]:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    "SELECT id, username, email, password_hash, credits, created_at, tushare_token, tushare_token_enabled FROM users WHERE username = ?",
                    (username,)
                )
                row = await cursor.fetchone()
                if not row:
                    return None
                return {
                    "id": row[0],
                    "username": row[1],
                    "email": row[2],
                    "password_hash": row[3],
                    "credits": row[4],
                    "created_at": row[5],
                    "tushare_token": row[6] if len(row) > 6 else None,
                    "tushare_token_enabled": bool(row[7]) if len(row) > 7 else False,
                }
        except Exception as e:
            print(f"❌ 查询用户失败: {e}")
            return None

    async def get_user_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    "SELECT id, username, email, password_hash, credits, created_at, tushare_token, tushare_token_enabled FROM users WHERE email = ?",
                    (email,)
                )
                row = await cursor.fetchone()
                if not row:
                    return None
                return {
                    "id": row[0],
                    "username": row[1],
                    "email": row[2],
                    "password_hash": row[3],
                    "credits": row[4],
                    "created_at": row[5],
                    "tushare_token": row[6] if len(row) > 6 else None,
                    "tushare_token_enabled": bool(row[7]) if len(row) > 7 else False,
                }
        except Exception as e:
            print(f"❌ 通过邮箱查询用户失败: {e}")
            return None

    async def get_user_credits_by_id(self, user_id: int) -> Optional[int]:
        """按用户ID获取剩余积分。"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    "SELECT credits FROM users WHERE id = ?",
                    (user_id,)
                )
                row = await cursor.fetchone()
                if not row:
                    return None
                return int(row[0]) if row[0] is not None else 0
        except Exception as e:
            print(f"❌ 查询用户积分失败: {e}")
            return None

    async def try_deduct_credits(self, user_id: int, amount: int) -> bool:
        """尝试扣减用户积分；余额不足则返回 False，不扣减。"""
        if amount <= 0:
            return True
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE users SET credits = credits - ? WHERE id = ? AND credits >= ?",
                    (amount, user_id, amount)
                )
                # SQLite中可用 changes() 判断受影响行数
                cursor = await db.execute("SELECT changes()")
                changes = (await cursor.fetchone())[0]
                if changes and int(changes) > 0:
                    await db.commit()
                    return True
                return False
        except Exception as e:
            print(f"❌ 扣减积分失败: {e}")
            return False

    async def add_credits(self, user_id: int, amount: int) -> bool:
        """为用户增加积分（可用于管理员充值或活动发放）。"""
        if amount <= 0:
            return True
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "UPDATE users SET credits = credits + ? WHERE id = ?",
                    (amount, user_id)
                )
                await db.commit()
                return True
        except Exception as e:
            print(f"❌ 增加积分失败: {e}")
            return False

    async def set_user_tushare_token(self, user_id: int, token: Optional[str], enabled: Optional[bool] = None, only_update_enabled: bool = False) -> bool:
        """设置或清空用户的 Tushare Token，并可选设置启用状态。
        
        Args:
            user_id: 用户ID
            token: Token值，传入空字符串或 None 将清空
            enabled: 是否启用，None 表示不修改当前状态
            only_update_enabled: 仅更新启用状态，不修改token（当用户只想切换开关时）
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                if only_update_enabled and enabled is not None:
                    # 仅更新启用状态，不改变 token
                    await db.execute(
                        "UPDATE users SET tushare_token_enabled = ? WHERE id = ?",
                        (1 if enabled else 0, user_id)
                    )
                elif enabled is not None:
                    # 同时更新 token 和启用状态
                    await db.execute(
                        "UPDATE users SET tushare_token = ?, tushare_token_enabled = ? WHERE id = ?",
                        ((token or None), 1 if enabled else 0, user_id)
                    )
                else:
                    # 只更新 token，不改变启用状态
                    await db.execute(
                        "UPDATE users SET tushare_token = ? WHERE id = ?",
                        ((token or None), user_id)
                    )
                await db.commit()
                return True
        except Exception as e:
            print(f"❌ 设置用户 Tushare Token 失败: {e}")
            return False

    async def get_user_tushare_token_by_id(self, user_id: int) -> Optional[Dict[str, Any]]:
        """按用户ID获取 Tushare Token 和启用状态。
        
        Returns:
            包含 token 和 enabled 的字典，或 None
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    "SELECT tushare_token, tushare_token_enabled FROM users WHERE id = ?",
                    (user_id,)
                )
                row = await cursor.fetchone()
                if not row:
                    return None
                return {
                    "token": row[0],
                    "enabled": bool(row[1]) if len(row) > 1 else False
                }
        except Exception as e:
            print(f"❌ 查询用户 Tushare Token 失败: {e}")
            return None

    async def can_send_code(self, email: str, purpose: str, min_interval_seconds: int = 60) -> bool:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    """
                    SELECT COUNT(*) FROM email_verification_codes
                    WHERE email = ? AND purpose = ? 
                      AND datetime(created_at) >= datetime('now', ?)
                    """,
                    (email, purpose, f'-{min_interval_seconds} seconds')
                )
                cnt = (await cursor.fetchone())[0]
                return cnt == 0
        except Exception as e:
            print(f"❌ 发送验证码频率检查失败: {e}")
            return False

    async def create_verification_code(self, email: str, code: str, purpose: str, ttl_minutes: int = 10) -> bool:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                expires_at = (datetime.now() + timedelta(minutes=ttl_minutes)).isoformat()
                await db.execute(
                    """
                    INSERT INTO email_verification_codes (email, code, purpose, expires_at)
                    VALUES (?, ?, ?, ?)
                    """,
                    (email, code, purpose, expires_at)
                )
                await db.commit()
                return True
        except Exception as e:
            print(f"❌ 保存验证码失败: {e}")
            return False

    async def verify_code(self, email: str, code: str, purpose: str) -> bool:
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    """
                    SELECT id FROM email_verification_codes
                    WHERE email = ? AND purpose = ? AND code = ? AND used = 0 
                      AND datetime(expires_at) > datetime('now')
                    ORDER BY created_at DESC LIMIT 1
                    """,
                    (email, purpose, code)
                )
                row = await cursor.fetchone()
                if not row:
                    return False
                rec_id = row[0]
                await db.execute(
                    "UPDATE email_verification_codes SET used = 1 WHERE id = ?",
                    (rec_id,)
                )
                await db.commit()
                return True
        except Exception as e:
            print(f"❌ 校验验证码失败: {e}")
            return False
    
    async def start_conversation(self, session_id: str = "default") -> int:
        """开始新的对话，返回conversation_id"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # 确保session存在
                await db.execute("""
                    INSERT OR IGNORE INTO chat_sessions (session_id) VALUES (?)
                """, (session_id,))
                
                # 获取下一个conversation_id
                cursor = await db.execute("""
                    SELECT COALESCE(MAX(conversation_id), 0) + 1 
                    FROM chat_records WHERE session_id = ?
                """, (session_id,))
                conversation_id = (await cursor.fetchone())[0]
                
                await db.commit()
                return conversation_id
                
        except Exception as e:
            print(f"❌ 开始对话失败: {e}")
            return 1  # 默认返回1
    
    async def save_conversation(
        self, 
        user_input: str,
        mcp_tools_called: List[Dict[str, Any]] = None,
        mcp_results: List[Dict[str, Any]] = None,
        ai_response: str = "",
        session_id: str = "default",
        conversation_id: int = None,
        username: Optional[str] = None,
        user_id: Optional[int] = None,
        attachments: List[Dict[str, Any]] = None,
        usage: Dict[str, Any] = None,
    ) -> Optional[int]:
        """保存完整的对话记录，返回插入记录ID（失败返回None）
        
        Args:
            user_input: 用户输入的问题
            mcp_tools_called: 调用的MCP工具列表
            mcp_results: MCP工具返回的结果列表
            ai_response: AI的回复内容
            session_id: 会话ID
            conversation_id: 对话ID，如果为None则自动生成
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                if conversation_id is None:
                    conversation_id = await self.start_conversation(session_id)
                
                # 将工具调用和结果转换为JSON
                mcp_tools_json = json.dumps(mcp_tools_called or [], ensure_ascii=False)
                mcp_results_json = json.dumps(mcp_results or [], ensure_ascii=False)
                attachments_json = json.dumps(attachments or [], ensure_ascii=False)
                
                cursor = await db.execute("""
                    INSERT INTO chat_records (
                        session_id, conversation_id, user_id, username, attachments, usage,
                        user_input, user_timestamp,
                        mcp_tools_called, mcp_results,
                        ai_response, ai_timestamp
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    session_id, conversation_id, user_id, username, attachments_json, json.dumps(usage or {}, ensure_ascii=False),
                    user_input, datetime.now().isoformat(),
                    mcp_tools_json, mcp_results_json,
                    ai_response, datetime.now().isoformat()
                ))
                
                await db.commit()
                inserted_id = cursor.lastrowid if cursor else None
                print(f"💾 对话记录已保存 (session={session_id}, conversation={conversation_id}, id={inserted_id})")
                return inserted_id
                
        except Exception as e:
            print(f"❌ 保存对话记录失败: {e}")
            return None

    # msid 相关方法已废弃

    async def get_threads_by_username(self, username: str, limit: int = 100) -> List[Dict[str, Any]]:
        """按用户名返回线程列表。"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    """
                    SELECT session_id, conversation_id,
                           MIN(created_at) AS first_time,
                           MAX(created_at) AS last_time,
                           COUNT(*) AS message_count,
                           COALESCE(
                               (SELECT user_input FROM chat_records cr2 
                                WHERE cr2.session_id = cr.session_id AND cr2.conversation_id = cr.conversation_id 
                                  AND cr2.username = cr.username
                                ORDER BY cr2.created_at ASC LIMIT 1),
                               ''
                           ) AS first_user_input
                    FROM chat_records cr
                    WHERE username = ?
                    GROUP BY session_id, conversation_id
                    ORDER BY last_time DESC
                    LIMIT ?
                    """,
                    (username, limit),
                )
                rows = await cursor.fetchall()
                columns = [desc[0] for desc in cursor.description]
                return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            print(f"❌ 按用户名获取线程列表失败: {e}")
            return []
    
    async def get_chat_history(
        self, 
        session_id: str = "default", 
        limit: int = 50,
        conversation_id: int = None
    ) -> List[Dict[str, Any]]:
        """获取聊天历史记录
        
        Args:
            session_id: 会话ID
            limit: 返回记录数量限制
            conversation_id: 特定对话ID，如果指定则只返回该对话
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                if conversation_id is not None:
                    # 获取特定对话
                    cursor = await db.execute("""
                        SELECT * FROM chat_records 
                        WHERE session_id = ? AND conversation_id = ?
                        ORDER BY created_at ASC
                    """, (session_id, conversation_id))
                else:
                    # 获取最近的对话记录
                    cursor = await db.execute("""
                        SELECT * FROM (
                            SELECT * FROM chat_records 
                            WHERE session_id = ?
                            ORDER BY created_at DESC 
                            LIMIT ?
                        ) ORDER BY created_at ASC
                    """, (session_id, limit))
                
                rows = await cursor.fetchall()
                columns = [desc[0] for desc in cursor.description]
                
                records = []
                for row in rows:
                    record = dict(zip(columns, row))
                    
                    # 解析JSON字段
                    try:
                        record['mcp_tools_called'] = json.loads(record['mcp_tools_called'] or '[]')
                        record['mcp_results'] = json.loads(record['mcp_results'] or '[]')
                        record['attachments'] = json.loads(record.get('attachments') or '[]')
                        record['usage'] = json.loads(record.get('usage') or '{}')
                    except json.JSONDecodeError:
                        record['mcp_tools_called'] = []
                        record['mcp_results'] = []
                        record['attachments'] = []
                        record['usage'] = {}
                    
                    records.append(record)
                
                # 如果不是特定对话，需要反转顺序（最新的在前面）
                if conversation_id is None:
                    records.reverse()
                
                return records
                
        except Exception as e:
            print(f"❌ 获取聊天历史失败: {e}")
            return []

    async def get_chat_history_by_user(
        self,
        username: str,
        limit: int = 50,
        conversation_id: int = None,
        session_id: Optional[str] = None,
    ) -> List[Dict[str, Any]]:
        """获取指定用户的聊天历史，可选按会话过滤。"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                params = []
                sql = "SELECT * FROM chat_records WHERE username = ?"
                params.append(username)
                if session_id is not None:
                    sql += " AND session_id = ?"
                    params.append(session_id)
                if conversation_id is not None:
                    sql += " AND conversation_id = ? ORDER BY created_at ASC"
                    params.append(conversation_id)
                else:
                    sql += " ORDER BY created_at DESC LIMIT ?"
                    params.append(limit)
                cursor = await db.execute(sql, tuple(params))
                rows = await cursor.fetchall()
                columns = [desc[0] for desc in cursor.description]
                records = []
                for row in rows:
                    record = dict(zip(columns, row))
                    try:
                        record['mcp_tools_called'] = json.loads(record['mcp_tools_called'] or '[]')
                        record['mcp_results'] = json.loads(record['mcp_results'] or '[]')
                        record['attachments'] = json.loads(record.get('attachments') or '[]')
                        record['usage'] = json.loads(record.get('usage') or '{}')
                    except json.JSONDecodeError:
                        record['mcp_tools_called'] = []
                        record['mcp_results'] = []
                        record['attachments'] = []
                        record['usage'] = {}
                    records.append(record)
                if conversation_id is None:
                    records.reverse()
                return records
        except Exception as e:
            print(f"❌ 获取用户聊天历史失败: {e}")
            return []
    
    async def clear_history(self, session_id: str = "default") -> bool:
        """清空指定会话的聊天历史"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute("""
                    DELETE FROM chat_records WHERE session_id = ?
                """, (session_id,))
                
                await db.execute("""
                    DELETE FROM chat_sessions WHERE session_id = ?
                """, (session_id,))
                
                await db.commit()
                print(f"🗑️ 已清空会话 {session_id} 的聊天历史")
                return True
                
        except Exception as e:
            print(f"❌ 清空聊天历史失败: {e}")
            return False

    async def delete_conversation(self, session_id: str, conversation_id: int) -> bool:
        """删除指定会话中的某个对话线程"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "DELETE FROM chat_records WHERE session_id = ? AND conversation_id = ?",
                    (session_id, conversation_id),
                )
                await db.commit()
                return True
        except Exception as e:
            print(f"❌ 删除对话线程失败: {e}")
            return False

    async def delete_records_after(self, session_id: str, conversation_id: int, from_id_inclusive: int) -> bool:
        """删除某线程中自指定记录ID起(含该ID)的所有记录，用于编辑回溯重生。

        Args:
            session_id: 会话ID
            conversation_id: 线程ID
            from_id_inclusive: 起始记录ID（包含）
        """
        try:
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    "DELETE FROM chat_records WHERE session_id = ? AND conversation_id = ? AND id >= ?",
                    (session_id, conversation_id, from_id_inclusive),
                )
                await db.commit()
                print(f"🪓 已从 (session={session_id}, conversation={conversation_id}) 起始ID {from_id_inclusive} 删除后续记录")
                return True
        except Exception as e:
            print(f"❌ 回溯删除记录失败: {e}")
            return False
    
    async def get_stats(self) -> Dict[str, Any]:
        """获取数据库统计信息"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                # 总记录数
                cursor = await db.execute("SELECT COUNT(*) FROM chat_records")
                total_records = (await cursor.fetchone())[0]
                
                # 会话数
                cursor = await db.execute("SELECT COUNT(DISTINCT session_id) FROM chat_records")
                total_sessions = (await cursor.fetchone())[0]
                
                # 对话数
                cursor = await db.execute("SELECT COUNT(DISTINCT conversation_id) FROM chat_records")
                total_conversations = (await cursor.fetchone())[0]
                
                # 最近记录时间
                cursor = await db.execute("SELECT MAX(created_at) FROM chat_records")
                latest_record = (await cursor.fetchone())[0]
                
                return {
                    "total_records": total_records,
                    "total_sessions": total_sessions,
                    "total_conversations": total_conversations,
                    "latest_record": latest_record,
                    "database_path": self.db_path
                }
                
        except Exception as e:
            print(f"❌ 获取统计信息失败: {e}")
            return {}
    
    async def create_shared_snapshot(self, records: List[Dict[str, Any]], created_by_user_id: int = None, created_by_username: str = None) -> str:
        """创建分享快照，返回 share_id。"""
        try:
            share_id = uuid.uuid4().hex  # 不可推断ID
            async with aiosqlite.connect(self.db_path) as db:
                await db.execute(
                    """
                    INSERT INTO shared_snapshots (share_id, data, created_by_user_id, created_by_username)
                    VALUES (?, ?, ?, ?)
                    """,
                    (share_id, json.dumps(records or [], ensure_ascii=False), created_by_user_id, created_by_username)
                )
                await db.commit()
            return share_id
        except Exception as e:
            print(f"❌ 创建分享快照失败: {e}")
            return ""

    async def get_shared_snapshot(self, share_id: str) -> List[Dict[str, Any]]:
        """按 share_id 读取分享快照，失败返回空数组。"""
        try:
            async with aiosqlite.connect(self.db_path) as db:
                cursor = await db.execute(
                    "SELECT data FROM shared_snapshots WHERE share_id = ? LIMIT 1",
                    (share_id,)
                )
                row = await cursor.fetchone()
                if not row:
                    return []
                try:
                    return json.loads(row[0] or "[]")
                except Exception:
                    return []
        except Exception as e:
            print(f"❌ 读取分享快照失败: {e}")
            return []
    
    async def close(self):
        """关闭数据库连接（在aiosqlite中不需要显式关闭）"""
        pass