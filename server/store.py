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
                id       INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id  INTEGER NOT NULL,
                bankno   TEXT NOT NULL,
                suiid    TEXT NOT NULL,
                type     TEXT NOT NULL DEFAULT '',
                provider TEXT NOT NULL DEFAULT ''
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
        # 老库升级:accounts.provider(2026-09)。神象云 / 旧随手记是两个完全不同的
        # 体系,同一张卡号的账户 id 在两边毫无关系 —— 把它们当一行存会直接导致
        # 「在旧账本里拿神象云 id 去查流水」这种 silent bug。
        # 老数据来自 conf.json 的 accounts,而 conf.json 用的是神象云 id,所以一并回填成 'shenxiang'。
        accCols = _columns(conn, "accounts")
        if "provider" not in accCols:
            try:
                conn.execute(
                    "ALTER TABLE accounts ADD COLUMN provider TEXT NOT NULL DEFAULT ''")
                conn.execute("UPDATE accounts SET provider = 'shenxiang' WHERE provider = ''")
            except Exception:
                pass
        # 老库升级:rules.book_id / rules.provider(2026-09)。记账规则之前只跟用户绑定,
        # 但不同账本的账户 id 和分类 id 各不相同 —— 必须把规则也跟账本绑定,
        # 否则会把 A 账本的分类 id 套到 B 账本上,对账/记账全乱。
        # 老规则这两列为空(孤儿),由 migrateOrphanRules / adoptOrphansToBook 兜底迁移。
        ruleCols = _columns(conn, "rules")
        if "book_id" not in ruleCols:
            try:
                conn.execute(
                    "ALTER TABLE rules ADD COLUMN book_id TEXT NOT NULL DEFAULT ''")
            except Exception:
                pass
        if "provider" not in ruleCols:
            try:
                conn.execute(
                    "ALTER TABLE rules ADD COLUMN provider TEXT NOT NULL DEFAULT ''")
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

    conf.json 里的映射都是神象云体系 —— 显式标记 provider='shenxiang'。
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
        saveAccounts(userId, accounts, provider="shenxiang")
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
# 账户映射 (银行账号 -> 账户 id,按 provider 分组)
#
# 神象云、旧随手记是两个完全不同的体系,同一个银行账号在两边有完全不同的账户 id。
# 因此映射必须分 provider 存 —— 不然用户切到旧账本时,会把神象云 id 拿来查旧流水,
# 永远空列表 —— 所有已记账条目都会显示成未记账。
# --------------------------------------------------------------------- #
def _providerNorm(p):
    """未知 provider 落到神象云(历史兼容):conf.json 的映射从来都是神象云。"""
    return p if p in ("shenxiang", "legacy") else "shenxiang"


def listAccounts(userId, provider=None):
    """列出该用户的所有账户映射。

    provider 给定时按 provider 过滤;不传时返回全部,前端能看到完整结构。
    """
    with getConn() as conn:
        sql = "SELECT id, bankno, suiid, type, provider FROM accounts WHERE user_id = ?"
        params = [userId]
        if provider:
            sql += " AND provider = ?"
            params.append(_providerNorm(provider))
        sql += " ORDER BY provider, bankno, id"
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def saveAccounts(userId, accounts, provider=None):
    """保存账户映射。

    provider 缺省时:整张表重写,每条记录按其 provider 字段保存(没有则按
    'shenxiang' 处理)。这样单 provider 时代的全量覆盖语义不变。
    provider 给定时:只覆盖该 provider 下的行,另一个 provider 的映射原样保留
    —— 用户在不同账本里分别维护映射,互不打架。
    """
    rows = []
    for a in (accounts or []):
        rows.append({"bankno": a.get("bankno", ""),
                     "suiid": a.get("suiid", ""),
                     "type": a.get("type", ""),
                     "provider": _providerNorm(a.get("provider") or provider or "")})
    with getConn() as conn:
        if provider:
            # 仅覆盖指定 provider,保留另一份
            conn.execute(
                "DELETE FROM accounts WHERE user_id = ? AND provider = ?",
                (userId, _providerNorm(provider)))
        else:
            conn.execute("DELETE FROM accounts WHERE user_id = ?", (userId,))
        for r in rows:
            conn.execute(
                "INSERT INTO accounts (user_id, bankno, suiid, type, provider) "
                "VALUES (?, ?, ?, ?, ?)",
                (userId, r["bankno"], r["suiid"], r["type"], r["provider"]))
        conn.commit()
    return listAccounts(userId)


def findAccount(userId, bankno, provider=None):
    """按卡号找映射。provider 缺省时按 (userId, bankno) 取一条;有 provider
    则只在该 provider 范围内找 —— 这是修 silent-bug 的关键。
    """
    with getConn() as conn:
        if provider:
            row = conn.execute(
                "SELECT * FROM accounts WHERE user_id = ? AND bankno = ? AND provider = ?",
                (userId, bankno, _providerNorm(provider))).fetchone()
        else:
            row = conn.execute(
                "SELECT * FROM accounts WHERE user_id = ? AND bankno = ? "
                "LIMIT 1", (userId, bankno)).fetchone()
        return dict(row) if row else None


# --------------------------------------------------------------------- #
# 记账规则
# --------------------------------------------------------------------- #
RULE_COLUMNS = ("id, book_id, provider, conditions, op, catid, op_suiid, memo, "
                "priority, hit_count, last_hit, created_at")


def listRules(userId, bookId=None, provider=None):
    """返回该用户的规则,优先级高的在前(与匹配顺序一致)。

    bookId 给定时只返回该账本(provider 也必须一致)的规则 —— 不同账本的账户和
    分类各不相同,规则必须按账本独立维护,否则会把 A 账本的分类 id 套到 B 账本上。
    bookId 为空(老调用方 / 测试)时返回全部,保持向后兼容。
    """
    with getConn() as conn:
        sql = "SELECT %s FROM rules WHERE user_id = ?" % RULE_COLUMNS
        params = [userId]
        if bookId:
            sql += " AND book_id = ? AND provider = ?"
            params.extend([bookId, _providerNorm(provider)])
        sql += " ORDER BY priority DESC, id"
        rows = conn.execute(sql, params).fetchall()
        return [dict(r) for r in rows]


def addRule(userId, rule, bookId="", provider=""):
    """新增规则。rule: {conditions(list), op, catid, opSuiid, memo, priority}

    bookId / provider 把规则绑定到具体账本 —— 不同账本独立维护规则。
    不传则落到「未归属」(book_id=''),由 migrateOrphanRules / adoptOrphansToBook 兜底迁移。
    """
    with getConn() as conn:
        cur = conn.execute(
            "INSERT INTO rules (user_id, book_id, provider, conditions, op, catid, op_suiid, memo, "
            "priority, hit_count, last_hit, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, NULL, ?)",
            (userId, bookId, _providerNorm(provider),
             json.dumps(rule.get("conditions") or [], ensure_ascii=False),
             rule["op"], rule.get("catid"), rule.get("opSuiid"),
             rule.get("memo"), int(rule.get("priority") or 0),
             datetime.now().isoformat(timespec="seconds")))
        conn.commit()
        return cur.lastrowid


def adoptOrphansToBook(userId, bookId, provider=""):
    """把该用户的「无账本归属」规则(历史数据)绑定到指定账本。

    触发条件: 用户切换到某账本,且该账本当前没有任何规则 —— 否则不动,
    避免把老规则错误塞进已配好规则的账本。幂等: 一旦绑定,后续不再有孤儿规则。
    这样既能保住老数据,又不会在不同账本间重复。
    """
    if not bookId:
        return 0
    with getConn() as conn:
        cnt = conn.execute(
            "SELECT COUNT(*) AS c FROM rules WHERE user_id = ? AND book_id = ? AND provider = ?",
            (userId, bookId, _providerNorm(provider))).fetchone()["c"]
        if cnt > 0:
            return 0
        cur = conn.execute(
            "UPDATE rules SET book_id = ?, provider = ? "
            "WHERE user_id = ? AND (book_id IS NULL OR book_id = '')",
            (bookId, _providerNorm(provider), userId))
        conn.commit()
        return cur.rowcount


def migrateOrphanRules():
    """启动期一次性迁移: 把老规则(无账本归属)绑定到用户最后使用的账本。

    用户还没保存过账本(book_id='')则暂不绑定,等其首次选账本时由
    adoptOrphansToBook 兜底。保证老规则不丢,同时逐步收敛到「每账本独立」。
    """
    with getConn() as conn:
        users = conn.execute("SELECT id, book_id, book_provider FROM users").fetchall()
        for u in users:
            bid = u["book_id"]
            if not bid:
                continue
            conn.execute(
                "UPDATE rules SET book_id = ?, provider = ? "
                "WHERE user_id = ? AND (book_id IS NULL OR book_id = '')",
                (bid, _providerNorm(u["book_provider"]), u["id"]))
        conn.commit()


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
    """从 conf.json 导入账户映射(老规则的 catid 在神象云下无效,不导入)。

    历史调用方未传 provider —— 显式打 'shenxiang' 标签,避免和未来的
    'legacy' 映射混在一起。
    """
    if conf.get("accounts"):
        saveAccounts(userId, conf["accounts"], provider="shenxiang")
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
                book_id    TEXT NOT NULL DEFAULT '',
                provider   TEXT NOT NULL DEFAULT '',
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
migrateOrphanRules()
