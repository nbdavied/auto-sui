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
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  INTEGER NOT NULL,
                exp      TEXT NOT NULL,
                op       TEXT NOT NULL,
                catid    TEXT,
                op_suiid TEXT,
                memo     TEXT
            )
        """)
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
                "INSERT INTO users (sui_username, book_id, created_at) VALUES (?, '', ?)",
                (suiUsername, datetime.now().isoformat(timespec="seconds")))
            conn.commit()
            user = {"id": cur.lastrowid, "sui_username": suiUsername, "book_id": ""}
    maybeImportFromConf(user["id"], suiUsername)
    return user


def setBookId(userId, bookId):
    with getConn() as conn:
        conn.execute("UPDATE users SET book_id = ? WHERE id = ?", (bookId, userId))
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
def listRules(userId):
    with getConn() as conn:
        rows = conn.execute(
            "SELECT id, exp, op, catid, op_suiid, memo FROM rules "
            "WHERE user_id = ? ORDER BY id", (userId,)).fetchall()
        return [dict(r) for r in rows]


def addRule(userId, rule):
    with getConn() as conn:
        cur = conn.execute(
            "INSERT INTO rules (user_id, exp, op, catid, op_suiid, memo) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (userId, rule["exp"], rule["op"], rule.get("catid"),
             rule.get("opSuiid"), rule.get("memo")))
        conn.commit()
        return cur.lastrowid


def deleteRule(userId, ruleId):
    with getConn() as conn:
        conn.execute("DELETE FROM rules WHERE user_id = ? AND id = ?", (userId, ruleId))
        conn.commit()


def importFromConf(userId, conf):
    """从 conf.json 导入账户映射与规则(迁移老配置用)。"""
    if conf.get("accounts"):
        saveAccounts(userId, conf["accounts"])
    n = 0
    for rule in conf.get("rules", []):
        addRule(userId, rule)
        n += 1
    return {"accounts": len(conf.get("accounts", [])), "rules": n}


initDb()
