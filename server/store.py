# -*- coding: utf-8 -*-
"""SQLite 存储层。

安全约定: 这里**只存配置和规则**,绝不存用户密码。
随手记账号密码由浏览器保存,每次请求带来,服务端仅在内存中使用。
"""
import os
import json
import sqlite3
from datetime import datetime

DB_PATH = os.environ.get("AUTO_SUI_DB", os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "autosui.db"))


def getConn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def initDb():
    with getConn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                sui_username TEXT UNIQUE NOT NULL,
                book_id      TEXT NOT NULL DEFAULT '',
                book_provider TEXT NOT NULL DEFAULT '',
                created_at   TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS accounts (
                id      INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                bankno  TEXT NOT NULL,
                suiid   TEXT NOT NULL,
                type    TEXT NOT NULL DEFAULT ''
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS rules (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                conditions TEXT NOT NULL,
                op         TEXT NOT NULL,
                catid      TEXT,
                op_suiid   TEXT,
                memo       TEXT,
                priority   INTEGER NOT NULL DEFAULT 0,
                hit_count  INTEGER NOT NULL DEFAULT 0,
                last_hit   TEXT,
                created_at TEXT
            )
        """)
        # 老库升级:book_provider 列(2026-09)。失败也无害 —— PRAGMA 加列是幂等的。
        cols = _columns(conn, "users")
        if "book_provider" not in cols:
            try:
                conn.execute("ALTER TABLE users ADD COLUMN book_provider TEXT NOT NULL DEFAULT ''")
            except Exception:
                pass
        conn.commit()


# --------------------------------------------------------------------- #
# 用户
# --------------------------------------------------------------------- #
CONF_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                         "conf.json")


def maybeImportFromConf(userId, username):
    """首次使用时,把 conf.json 里已沉淀的账户映射自动导入。

    只导账户映射,不导规则: 规则里的 catid 是老随手记的分类 id,
    在神象云下无效,需要单独迁移后才能启用。
    """
    if listAccounts(userId):
        return 0
    if not os.path.exists(CONF_PATH):
        return 0
    try:
        with open(CONF_PATH, encoding="utf-8") as f:
            conf = json.load(f)
    except Exception:
        return 0
    if conf.get("username") != username:
        return 0
    accounts = conf.get("accounts") or []
    if accounts:
        saveAccounts(userId, accounts)
    return len(accounts)


def getOrCreateUser(suiUsername):
    with getConn() as conn:
        row = conn.execute("SELECT * FROM users WHERE sui_username = ?",
                           (suiUsername,)).fetchone()
        if row:
            user = dict(row)
        else:
            cur = conn.execute(
                "INSERT INTO users (sui_username, book_id, book_provider, created_at) "
                "VALUES (?, '', '', ?)",
                (suiUsername, datetime.now().isoformat(timespec="seconds")))
            conn.commit()
            user = {"id": cur.lastrowid, "sui_username": suiUsername,
                    "book_id": "", "book_provider": ""}
    maybeImportFromConf(user["id"], suiUsername)
    return user


def setBookId(userId, bookId, provider=""):
    """记住当前账号最后选择的账本 + 来源(provider)。

    provider 缺省时(如旧调用方)不覆盖已有 provider,以免「忘记选账本
    又选一次 bookId」的情况下把 provider 清空。
    """
    with getConn() as conn:
        if provider:
            conn.execute(
                "UPDATE users SET book_id = ?, book_provider = ? WHERE id = ?",
                (bookId, provider, userId))
        else:
            conn.execute(
                "UPDATE users SET book_id = ? WHERE id = ?",
                (bookId, userId))
        conn.commit()


def getUser(userId):
    with getConn() as conn:
        row = conn.execute("SELECT * FROM users WHERE id = ?", (userId,)).fetchone()
        return dict(row) if row else None


# --------------------------------------------------------------------- #
# 账户映射 (银行账号 -> 神象云账户 id)
# --------------------------------------------------------------------- #
def listAccounts(userId):
    with getConn() as conn:
        rows = conn.execute(
            "SELECT id, bankno, suiid, type FROM accounts WHERE user_id = ? ORDER BY id",
            (userId,)).fetchall()
        return [dict(r) for r in rows]


def saveAccounts(userId, accounts):
    """整体覆盖保存账户映射。accounts: [{bankno, suiid, type}]"""
    with getConn() as conn:
        conn.execute("DELETE FROM accounts WHERE user_id = ?", (userId,))
        for a in accounts:
            conn.execute(
                "INSERT INTO accounts (user_id, bankno, suiid, type) VALUES (?, ?, ?, ?)",
                (userId, a.get("bankno", ""), a.get("suiid", ""), a.get("type", "")))
        conn.commit()
    return listAccounts(userId)


def findAccount(userId, bankno):
    with getConn() as conn:
        row = conn.execute(
            "SELECT * FROM accounts WHERE user_id = ? AND bankno = ?",
            (userId, bankno)).fetchone()
        return dict(row) if row else None


# --------------------------------------------------------------------- #
# 记账规则
# --------------------------------------------------------------------- #
RULE_COLUMNS = ("id, conditions, op, catid, op_suiid, memo, "
                "priority, hit_count, last_hit, created_at")


def listRules(userId):
    """返回该用户的规则,优先级高的在前(与匹配顺序一致)。"""
    with getConn() as conn:
        rows = conn.execute(
            "SELECT %s FROM rules WHERE user_id = ? "
            "ORDER BY priority DESC, id" % RULE_COLUMNS, (userId,)).fetchall()
        return [dict(r) for r in rows]


def addRule(userId, rule):
    """新增规则。rule: {conditions(list), op, catid, opSuiid, memo, priority}"""
    with getConn() as conn:
        cur = conn.execute(
            "INSERT INTO rules (user_id, conditions, op, catid, op_suiid, memo, "
            "priority, hit_count, last_hit, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, 0, NULL, ?)",
            (userId, json.dumps(rule.get("conditions") or [], ensure_ascii=False),
             rule["op"], rule.get("catid"), rule.get("opSuiid"),
             rule.get("memo"), int(rule.get("priority") or 0),
             datetime.now().isoformat(timespec="seconds")))
        conn.commit()
        return cur.lastrowid


def updateRule(userId, ruleId, rule):
    """更新规则。只更新传进来的字段,没传的保持原值。"""
    fields = []
    values = []
    if "conditions" in rule:
        fields.append("conditions = ?")
        values.append(json.dumps(rule["conditions"] or [], ensure_ascii=False))
    for col, key in (("op", "op"), ("catid", "catid"), ("op_suiid", "opSuiid"),
                     ("memo", "memo"), ("priority", "priority")):
        if key in rule:
            fields.append("%s = ?" % col)
            values.append(int(rule[key]) if key == "priority" else rule[key])
    if not fields:
        return False
    values.extend([userId, ruleId])
    with getConn() as conn:
        cur = conn.execute(
            "UPDATE rules SET %s WHERE user_id = ? AND id = ?" % ", ".join(fields),
            values)
        conn.commit()
        return cur.rowcount > 0


def deleteRule(userId, ruleId):
    with getConn() as conn:
        conn.execute("DELETE FROM rules WHERE user_id = ? AND id = ?", (userId, ruleId))
        conn.commit()


def recordRuleHit(userId, ruleId):
    """规则命中时累加计数,便于在管理页看出哪些规则真的在用。"""
    with getConn() as conn:
        conn.execute(
            "UPDATE rules SET hit_count = hit_count + 1, last_hit = ? "
            "WHERE user_id = ? AND id = ?",
            (datetime.now().isoformat(timespec="seconds"), userId, ruleId))
        conn.commit()


def importFromConf(userId, conf):
    """从 conf.json 导入账户映射(老规则的 catid 在神象云下无效,不导入)。"""
    if conf.get("accounts"):
        saveAccounts(userId, conf["accounts"])
    return {"accounts": len(conf.get("accounts", [])), "rules": 0}


# --------------------------------------------------------------------- #
# 迁移: 老规则 exp 表达式 -> 结构化 conditions
# --------------------------------------------------------------------- #
def _columns(conn, table):
    return [r["name"] for r in conn.execute("PRAGMA table_info(%s)" % table)]


def migrateRules():
    """把旧版 exp 表达式规则转译成结构化条件。

    老表用 exp 列存表达式、靠 eval 执行。这里重建表并按 `字段 == '值'`
    的形式转译;转译不出来的规则直接丢弃 —— 宁可丢,也不留可执行代码。
    """
    from server.reconcile import expToConditions
    with getConn() as conn:
        if "conditions" in _columns(conn, "rules"):
            return {"migrated": 0, "dropped": 0, "skipped": True}
        rows = [dict(r) for r in conn.execute(
            "SELECT id, user_id, exp, op, catid, op_suiid, memo FROM rules").fetchall()]

        conn.execute("ALTER TABLE rules RENAME TO rules_old_exp")
        conn.execute("""
            CREATE TABLE rules (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id    INTEGER NOT NULL,
                conditions TEXT NOT NULL,
                op         TEXT NOT NULL,
                catid      TEXT,
                op_suiid   TEXT,
                memo       TEXT,
                priority   INTEGER NOT NULL DEFAULT 0,
                hit_count  INTEGER NOT NULL DEFAULT 0,
                last_hit   TEXT,
                created_at TEXT
            )
        """)
        now = datetime.now().isoformat(timespec="seconds")
        moved, dropped = 0, 0
        for r in rows:
            conds = expToConditions(r.get("exp") or "")
            if not conds:
                dropped += 1
                continue
            conn.execute(
                "INSERT INTO rules (user_id, conditions, op, catid, op_suiid, memo, "
                "priority, hit_count, last_hit, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 0, 0, NULL, ?)",
                (r["user_id"], json.dumps(conds, ensure_ascii=False), r["op"],
                 r.get("catid"), r.get("op_suiid"), r.get("memo"), now))
            moved += 1
        conn.execute("DROP TABLE rules_old_exp")
        conn.commit()
        return {"migrated": moved, "dropped": dropped, "skipped": False}


initDb()
migrateRules()
