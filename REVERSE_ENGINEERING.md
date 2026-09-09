# 神象云账本接口逆向成果

> 逆向时间：2026-09-09。依据：`captures/www.feidee.com.har`（用户抓包）+ 前端 `app.js` 源码。

## 一、认证机制

### 1. 登录（OAuth2 password 模式）

```
GET https://auth.feidee.net/v2/oauth2/authorize
  ?grant_type=password_web
  &encode_version=V4
  &scope=user
  &username=<邮箱>
  &password=<sha1(明文密码)>
  &vcid=
  &vid=
```

请求头（关键）：
| 头 | 值 |
|---|---|
| App-Id | cab-web |
| Type | MD5-H5 |
| Minor-Version | 2 |
| Client-Key | `520BFC1EA31D45678A9B865668A47F40`（固定） |
| Nonce-Str | 16 位随机数字 |
| Timestamp | 毫秒时间戳 |
| Sign | `md5(Client-Key + Nonce-Str + Timestamp)`（密钥为空串） |
| Device | 设备 JSON |

响应：`{access_token, refresh_token, token_type: "Bearer", expires_in}`

### 2. 业务接口签名

所有 `yun.feidee.net/cab-*` 接口需携带：
| 头 | 值 |
|---|---|
| Authorization | `Bearer <access_token>` |
| Trading-Entity | 账本 id（切换账本即改此头） |
| Device | 设备 JSON |
| Client-Key | `PiVEoJM9OHFS8xFlnD3CuSrJgRgyVLwS`（固定） |
| Nonce-Str | 16 位随机数字 |
| Timestamp | 毫秒 |
| Sign | `md5(Client-Key + Nonce-Str + Timestamp + "pQhGxs0I84zQgeU8")` |

> 注：`Client-Key` 与密钥均为前端硬编码，非登录下发。

## 二、关键接口清单

| 用途 | 方法 | 路径 |
|---|---|---|
| 账本列表 | GET | `/cab-index-ws/v3/book-group/cloud` |
| 当前账本信息 | GET | `/cab-config-ws/v3/book/info` |
| 账户列表 | GET | `/cab-config-ws/v2/account-book/accounts?scene=Accounting&operation_codes=C` |
| 分类列表 | GET | `/cab-config-ws/v2/account-book/categories?trade_type=&operation_codes=C` |
| 成员列表 | GET | `/cab-config-ws/v2/account-book/members` |
| 支出记账 | POST | `/cab-accounting-ws/v2/account-book/transaction/expense` |
| 收入记账 | POST | `/cab-accounting-ws/v2/account-book/transaction/income` |
| 转账记账 | POST | `/cab-accounting-ws/v2/account-book/transaction/transfer` |
| 流水查询 | POST | `/cab-query-ws/v2/statistics/transactions` |

## 三、记账请求体

```jsonc
// 支出
{"business_type":"Expense","account":{"id":".."},"category":{"id":".."},
 "amount":"1.23","remark":"备注","transaction_time":<毫秒>,
 "member":{"id":".."} /*可选*/}

// 收入（同支出，business_type=Income）
// 转账
{"business_type":"Transfer","from_account":{"id":".."},"to_account":{"id":".."},
 "from_amount":"0.66","to_amount":"0.66","remark":"备注","transaction_time":<毫秒>}
```

- `amount` 为字符串。
- `member/merchant/project` 均为可选维度（实测不带 merchant/project 可正常记账）。
- `transaction_time` 为毫秒时间戳。

## 四、流水查询与字段映射

请求：
```jsonc
{"query":{"account_ids":["<账户id>"],"start_time":<毫秒>,"end_time":<毫秒>},
 "sort":{"order_by":"DESC","sort_by":"ACCOUNT_TIME"},
 "page":{"page_offset":0,"page_size":200},"extend":{"scene":"Account"}}
```
响应：`{data:[...], paging:{has_more}}`

`business_type` 与老随手记 `tranType` 映射：
| 神象云 business_type | 老 tranType | 说明 |
|---|---|---|
| Expense | 1 | 支出 |
| Transfer | 2 | 转账（`from_account`=转出 buyer，`to_account`=转入 seller） |
| Income | 5 | 收入 |
| Balance_Changed | - | 余额调整，对账时跳过 |

## 五、已验证结论

- ✅ 登录、签名算法（md5）全部实测通过。
- ✅ 账户/分类/成员/流水查询全部实测通过。
- ✅ 支出/收入/转账记账全部实测通过（HTTP 201）。
- ✅ `merchant`/`project` 维度可省略，`member` 默认账本主人即可。
