# 贡献指南

Python 3.10 及以上可用于开发。建议在虚拟环境中执行：

```bash
python -m pip install -e '.[dev]'
python -m unittest discover -s tests -v
python scripts/check_public_tree.py
python -m build
```

提交前说明问题、改动和验证方式，尽量保持原有 CLI 参数兼容。接口数据请使用合成样例；现有离线测试不需要真实账号或网络请求。涉及实际 Android 行为的新测试，应先在授权设备上确认交互和等待条件。

请勿提交真实 token、手机号、短信验证码、Cookie、浏览器 profile、抓包或会员下载内容。排查问题时仅提供脱敏错误和复现步骤。使用自定义下载目录或 DUKU_CONFIG_DIR 时，须额外配置忽略规则。`.gitignore` 不会保护已经被 Git 跟踪的文件，也不应使用 `git add -f` 绕过过滤。

使用 `git diff --cached` 核对待提交内容，执行隐私检查。贡献代码按项目现有 GPLv3 许可证提供，并保留所引用代码的出处与许可说明。
