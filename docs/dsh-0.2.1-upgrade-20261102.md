# DSH 0.2.1-rc.5 升级记录

日期：2026-11-02。范围：本机全局 `@deepseek-ai/dsh`、咕嘎 headless sidecar 接入、旧配置迁移和真实工具调用验证。

## 升级前状态

- 本机：`0.1.7-rc.2`，最后修改于 2026-09-24。
- npm `latest`：`0.2.1-rc.5`。
- 咕嘎正式对话和桌面工具仍由自己的 `SelfAgent` 运行；DSH 只是可选的 `dsh_task` 长任务 sidecar。
- 旧 DSH 的用户凭据已过期。单独启动 DSH 返回 `api_key_expired`。

## 已完成

1. 备份旧 `dsh`、`dsh.cmd`、`dsh.ps1`、package 元数据到 `runtime/upgrades/dsh-0.1.7-rc.2-20261102/`。
2. 将全局 npm 包升级到 `0.2.1-rc.5`。
3. 确认新版仍支持咕嘎使用的：

   ```text
   dsh --profile headless --json -
   ```

4. 向 DSH 传入咕嘎 `ai_config.json` 中的 `OPENCODE_GO_API_KEY`，并在开发态和打包态都生效。这样不再依赖 DSH 自己保存的旧凭据。
5. 备份并移除旧 `~/.dsh/cordis.patch.yml` 中已被新版删除的 `ui-settings-general` 覆盖。`dsh --profile headless --dump-config` 不再报补丁目标不存在。
6. 增加回滚脚本 `tools/rollback_dsh.ps1`，默认恢复 `0.1.7-rc.2`。

## 真实验证

- CLI 纯文字：返回 `READY`，退出码 0。
- `DshManager`：会话、状态、最终结果和退出码解析正确。
- 工具调用：DSH 调用只读 PowerShell `Get-Location`，返回项目工作目录，随后正常完成第二轮总结。
- 新版事件已确认包含 `session`、`status`、`text`、`thinking`、`tool_call`、`tool_result` 和 `final`；咕嘎现有解析仍兼容。

## 限制

- `0.2.1-rc.5` 仍是 RC/开发者预览版本，后续接口可能变化。
- npm 报告部分原生依赖安装脚本未执行；本次只读 PowerShell 工具已真实可用，但尚未逐项验证 DSH 的所有插件与终端后端。
- 已更新全局 CLI。若已有打包成品，需重新运行打包流程才会携带新版本；源码运行时直接使用更新后的 PATH。

## 回滚

```powershell
powershell -ExecutionPolicy Bypass -File tools/rollback_dsh.ps1
```

旧配置备份在 `runtime/upgrades/dsh-0.1.7-rc.2-20261102/`。
