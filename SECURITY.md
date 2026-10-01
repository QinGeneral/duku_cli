# 安全与私人信息

不要在公开 issue、pull request、日志或截图中粘贴账号凭据、手机号、短信验证码、完整抓包或带签名的媒体 URL。报告时说明复现条件，并提供脱敏后的错误。

登录凭据默认存于 `~/.duku/config.json`；短信验证浏览器资料位于该配置目录下的 `captcha-chrome-profile`，不可写入时可能回退到系统临时目录。使用者应保护这些本地文件的访问权限，尤其在共享设备上。

若凭据意外出现在公开仓库或附件中，先使其失效并重新登录，再清除公开文件及历史记录。只删除最新版本中的字符串不足以清除 Git 历史。这个开源副本使用全新的 Git 仓库，不复用历史提交。

涉及敏感账号信息的问题，请通过 GitHub 私密漏洞报告入口提交：
https://github.com/QinGeneral/duku_cli/security/advisories/new

不要在公开 issue 或 pull request 中附带凭据或完整抓包。
