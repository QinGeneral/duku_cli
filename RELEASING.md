# 发布维护

发行名称 `duku-cli`，命令入口 `duku`。GitHub 仓库：
https://github.com/QinGeneral/duku_cli

GitHub Actions 使用 `.github/workflows/release.yml`，通过 PyPI Trusted Publishing（OIDC）发布，发布 environment 为 `pypi`。不需要配置长期 PyPI token。

首次注册 pending publisher 时，以下字段必须精确一致：

| 字段 | 值 |
| --- | --- |
| PyPI Project Name | `duku-cli` |
| GitHub Owner | `QinGeneral` |
| Repository name | `duku_cli` |
| Workflow name | `release.yml` |
| Environment name | `pypi` |

后续发布前更新 `pyproject.toml` 中版本并提交，版本须未在 PyPI 发布过。先通过 CI，再为声明该版本的提交打对应标签，例如版本为 0.1.0 时：

```bash
git tag -a v0.1.0 -m 'v0.1.0'
git push origin v0.1.0
```

发布工作流分别构建和上传：只有 publish job 有 `id-token: write`。build job 执行源码隐私检查、现有离线测试，并用 `uv build --no-sources` 构建 wheel 和 sdist，随后在源码目录外检查两个安装包。

本地构建使用新建的独立输出目录，不复用旧的 dist 内容：

```bash
uv build --no-sources --out-dir /tmp/duku-cli-release
```

上传前确认归档中没有配置、凭据、抓包或下载内容。线上验证需在源码目录之外从 PyPI 强制刷新安装，检查发行版本以及 `duku --help`。

已发布版本不能覆盖；修复发布配置时先阅读失败 step，若尚未上传可重新运行原工作流，若已上传则使用新的版本。
