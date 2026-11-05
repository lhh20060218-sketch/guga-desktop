# 长语音快捷执行与稳定性修复（2026-11-04）

源码版本：`2026-11-04.long-voice-stability.1`。本次公开源码同时包含此前尚未上传的常用形态、可删除用户记忆、联网问答、屏幕辅助、浏览器会话和后台任务进度改动。历史EXE及私人测试包未重新打包。

## 修复

- 网站命令支持“你能帮我打开一下 GitHub 官网吗”“打开一个百度的网站”“用默认浏览器打开网址”等明确口语；复合任务、否定要求继续交给原路由。语音转写、本地补充文字和工具委派共享快捷执行结果，按本轮输入去重，迟到的模型工具调用不会再次打开网页。
- 浏览器启动保留Windows注册的参数。原实现只提取EXE，会丢掉豆包浏览器的`--single-argument`；现在通过Windows原生参数解析保留标记、把URL作为单个参数传递，不使用shell拼接。
- 启动网站和软件在工作线程运行，慢系统处理程序不再阻塞Qt语音事件循环。启动回执与页面加载结果分别表述。
- 语音转写触发快捷执行后，在本地抑制提前播报，同时完成原生函数调用及回执；取消旧回复可能使已经产生的函数调用没有结果回传。本轮对照中，该旧路径可在真实语音操作后复现远端中断；取消这一不必要的协议取消后，45秒和60秒语音复测均未中断。样本有限，不把时间相关性视为远端实现的完整根因证明。
- 新文字打断等待旧回复结束后再请求新回复；说话门禁不再被任务清理意外清空；迟到的旧`response.done`不会清掉新回复状态。
- 单轮取消/忙碌等协议拒绝保持会话，可恢复服务错误续接，额度、鉴权和明确配置错误仍停止。重连不向新会话发送旧工具ID，不重放桌面操作，保留可播报的任务结果。增加WebSocket保活与关闭码诊断，日志不记录音频、转写或凭据。
- 新公开配置默认`server_vad`、600毫秒停顿，通话/空闲时限均为0（手动结束）。旧配置不覆盖。补全`psutil`、`playwright`等依赖；本地配置、数据库、运行数据与私人包不进入本次发布。

## 验收证据与边界

离线检查覆盖快速路由、重复副作用、函数回执、取消顺序、说话门禁、额度保护、重连、Qt响应、记忆/问答隔离、屏幕及浏览器会话；命令和最终数量记录在本地`runtime/long-voice-qa-final-*.txt`。新增回归先在修改前运行，确实出现失败；并非只检查修改后的函数输出。

最终22组相关回归共275项全部通过；从Git暂存文件单独导出的无私人配置、无历史运行目录的源码另通过40项核心检查，关键模块和依赖导入成功。公开索引的290个Python文件语法检查通过，1274个索引文件的发布范围与凭据扫描通过。测试仍会报告既有GIF资源未关闭的`ResourceWarning`，不影响本次断言结果。

真实服务使用现有已确认免费额度的千问模型，没有更换模型或付费保护。所有输入均为合成语音/通用测试文字，不录制麦克风，不播放扬声器；后台是受控等待状态，不代表验收了任意复杂桌面任务。

| 场景 | 结果 |
| --- | --- |
| 连续四轮文字注入、屏幕事实及后台任务状态 | 60秒、0次断线、4轮回复；首音频约750—937毫秒，快捷操作反馈约2266毫秒 |
| 合成语音打开网站，原生函数回执路径 | 修复后45秒、0次断线、1次快捷执行 |
| 合成语音实际打开GitHub | 修复后60秒、0次断线、1次启动；speech_stopped后188毫秒完整转写，转写后约15毫秒提交启动；另读到“GitHub - 豆包浏览器”窗口标题 |

真实结果保存在`runtime/long-voice-qa/after-heartbeat.json`、`after-native-tool-turn.json`、`final-audio-browser.json`；这些本机证据不随公开仓库发布。诊断过程的失败样本也保留，未覆盖为成功。单次耗时不是平均值或P95，启动耗时不等于网络页面加载耗时，未进行数小时通话或真实麦克风声学验收。

协议处理参照[千问客户端事件](https://www.alibabacloud.com/help/en/model-studio/fun-audiochat-client-events)及[WebSocket交互与错误处理](https://docs.modelstudio.console.alibabacloud.com/en/model-studio/fun-audiochat-realtime-websocket-api)。原生工具收尾的稳定性结论来自本机复测，不推定服务端全部实现。

## 获取和复测

使用GitHub仓库的Download ZIP或`git pull`获取最新`main`源码，然后：

```powershell
python -m pip install -r requirements.txt
```

首次使用双击`首次配置.bat`填写自己的模型配置；升级保留已有配置。之后双击`启动企鹅.bat`，或`python launcher.py`。不要运行私人测试打包脚本来生成公开包。

核心离线检查：

```powershell
python -m unittest tools.test_long_voice_stability tools.test_realtime_voice tools.test_realtime_agent tools.test_voice_resilience tools.test_voice_conversation_controls tools.test_voice_call_e2e tools.test_responsive_voice tools.test_fast_and_speaker -q
```

有已确认的免费语音配置时，可显式进行有时限的服务复测：

```powershell
python tools/probe_long_voice_acceptance.py --live --audio-command --seconds 45 --label local-acceptance
```

加入`--open-browser`才执行合成语音指定的单次GitHub启动；默认使用受控执行器。探测最长90秒，结束后释放连接和测试线程。
