# auto-sui
随手记自动记账

为了节省随手记对账的时间，现在开始开发自动记账功能
先画个大饼，本系统将实现的目标：
1. 支持从邮箱提取贷记卡账单
2. 支持从银行网银导出的流水提取借记卡明细
3. 支持账户间转账的识别
4. 支持常见收支用途的识别

由于随手记没有提供api接口，所有对随手记的操作将模拟网页版随手记的交互。
目前只完成了登陆部分，验证了可行性，此处感谢[go-http/feidee](https://github.com/go-http/feidee)项目中用go语言实现提供的思路。

### gmail
gmail 通过 google api调用，需要在google cloud上开通gmail api，并下载 credentials.json 文件到目录中