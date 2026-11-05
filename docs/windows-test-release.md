# Windows私人测试版 2026.10.22.6

使用 `tools/build_windows_release.py` 生成独立目录，再用 `tools/finish_windows_release.py --stage-sidecar` 和 `tools/finish_windows_release.py` 制作安装器。PyInstaller与Inno Setup 7为构建依赖，接收者无需安装这些工具。

此版本按作者明确授权内置 OpenCode Go DeepSeek V4.1 Flash 与千问 Qwen-Audio-3.1-Realtime 配置，仅限私人测试。配置是可读取的，不属于密钥保护方案，目录 `build/`、`release-private/` 已忽略。没有发布到GitHub。

安装包携带Python运行时、Qt及音频插件、桌宠素材、《晴天》完整288.49秒翻唱、DSH与Node/PowerShell。用户不用录入声纹；默认音频设备在目标电脑重新选择。API需要联网，微信、默认浏览器等目标软件需要接收者安装并登录。

明确点歌时，千问直接调用 `perform_music`，默认《晴天》；本地转写快速路由与原生工具共用去重。暂停、继续、停止走播放器；普通聊天提到歌曲不触发。歌曲路径改为相对音乐库，解除开发电脑路径依赖。外放防回声模式唱歌时暂停麦克风，75秒暂停互动；耳机模式允许同时交流。

已确认：
- 100项回归与Qt气泡检查通过，涵盖快速网页/浏览器路由、微信流程、窗口发现、截图传递、完成回执和歌曲控制。
- 千问真实连接将点歌请求路由至本地《晴天》，约0.8秒；此协议测试没有上传麦克风录音。
- 独立Guga.exe在移除开发环境PATH后成功加载素材、音频库及两家模型配置，真实播放《晴天》超过3秒，正常退出。
- 完整EXE界面启动成功，状态回执显示新版语音路由、声纹关闭、完整访问开启。
- 附带DSH的独立Node启动与版本查询成功。DSH长任务以及不同电脑上的微信/浏览器实机操作仍需要接收者测试；不以单元测试替代外机验收。

本机音乐和配置验证报告在私人输出目录的 `binary-smoke.json` 和 `packaged-startup.json`；不包含API明文。安装器编译完成后生成 `SHA256.txt`。
