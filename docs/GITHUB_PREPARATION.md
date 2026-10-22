# GitHub 准备与发布边界

## 已采用的路线

在当前项目上做最小必要改进，复用识别、翻译、字幕、FFmpeg 与完整工作站。不更换框架，不增加在线模型服务，不产生 API 费用。

初筛参考：
- https://github.com/WEIFENG2333/VideoCaptioner ：识别、优化、翻译和合成；GPL-3.0。
- https://github.com/jianchang512/pyvideotrans ：视频翻译、字幕与配音；GPL-3.0。
- https://github.com/SubtitleEdit/subtitleedit ：字幕编辑；MIT。

本轮未复制这些候选项目的实现，也未切换到其代码库。未完成候选的维护活跃度、依赖、安全与迁移深评，不据此声称它们一定优于当前项目。

## 仓库内容

允许：src、config 中默认配置、tests、scripts、packaging、README、开发配置、文档和 CI 工作流。

排除：旧程序 LocalVideoAI、release、build、dist、vendor、models、test_assets、数据、日志、缓存、数据库、本机路径配置、密钥与环境文件。

## 上线前检查

1. 确认 GitHub 账号、仓库名与可见性。
2. 确认代码权属与是否授予开源许可证；本次没有擅自选择许可证。
3. 运行 `python scripts/audit_repository.py` 检查已跟踪和未忽略文件的大小、敏感文件与疑似密钥。
4. 用 `git status --short`、`git diff --cached --stat` 人工复核提交内容。
5. 源码提交至仓库；安装包以后通过 Release 附件分发，模型单独说明来源与许可。

CI 仅覆盖不依赖本机权重的指定测试，不宣称完整语音模型端到端验证。尚未配置远程仓库时不会自动推送。
