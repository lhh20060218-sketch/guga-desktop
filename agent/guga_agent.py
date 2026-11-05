# -*- coding: utf-8 -*-
"""
咕嘎管家 · 本机执行方值守程序 v0.6
作用：把您本机和网页上的咕嘎配对成同一账号——网页派"本机执行"的单，
     这里自动领单，真实拉起本机豆包干活，产物回传网页走同一套监工验收。
用法：
    python guga_agent.py <6位配对码>       # 配对码在网页 🩺自检 弹窗里点"生成配对码"
    python guga_agent.py                   # 不带参数会提示输入
安全：
    - 只在收到网页任务时操作本机 AI 软件（豆包），新对话隔离、不碰别的窗口
    - FAILSAFE 开启：鼠标甩到屏幕左上角立即紧急停手
    - Ctrl+C 退出值守；赛后删除整个目录即可，无任何残留
"""
import os
import sys
import json
import time
import threading
import urllib.request
import urllib.error

BASE = os.environ.get("GUGA_CLOUD", "http://39.107.48.60:3000")   # 云端大脑地址；可用环境变量 GUGA_CLOUD 指向自建服务
# 冻结成 exe 时 __file__ 指向临时解包目录 _MEIxxxxx，必须用 sys.executable 才是本体真实位置
if getattr(sys, 'frozen', False):
    HERE = os.path.dirname(os.path.abspath(sys.executable))
else:
    HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)


def api(path, data=None, token=None, timeout=20):
    req = urllib.request.Request(BASE + path, method="POST" if data is not None else "GET")
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("X-Agent-Token", token)
    body = json.dumps(data).encode("utf-8") if data is not None else None
    with urllib.request.urlopen(req, body, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8"))


def log(msg):
    print(f"[咕嘎本体 {time.strftime('%H:%M:%S')}] {msg}", flush=True)


AGENT_VERSION = "0.15"   # 随心跳上报：下次"跑的是哪一版"不用再靠文件时间猜


def local_caps():
    """本机能力清单：随配对/心跳上报，网页自检据此显示"这台电脑能不能真机干活"。"""
    caps = {"pyver": sys.version.split()[0], "platform": sys.platform, "agent": AGENT_VERSION}
    try:
        import pyautogui, pyperclip, pygetwindow, PIL  # noqa: F401
        caps["deps_ok"] = True
    except Exception:
        caps["deps_ok"] = False   # 只影响真机指挥；配对与心跳纯标准库即可
    return caps


def pair(code):
    import guga_selfcheck as sc
    chk = sc.run_check()
    log(f"本机自检：识别到 {len(chk['ai'])} 个可指挥的 AI 软件：{'、'.join(chk['ai']) or '无'}")
    device = f"{os.environ.get('COMPUTERNAME', 'PC')} · Windows"
    r = api("/api/agent/pair", {"code": code, "device": device, "selfcheck": chk,
                                "path": HERE, "caps": local_caps()})
    log(f"配对成功！已与网页账号「{r['user']}」绑定")
    return r["token"]


def run_job(job, token):
    """领到单：真实指挥本机豆包 → 每轮读完豆包回复先请示大脑 →
    大脑说是交付就交，说是在反问就按大脑拟好的话追问——绝不盲交、绝不死循环。
    视觉层：定位按钮、读回复都先"看"再动（see/locate），失败自动回退旧启发式。"""
    import guga_executor as dex
    dex.TOKEN = token   # 视觉请示要带执行方身份
    dex.CTX = {"taskId": job["taskId"], "stId": job["stId"]}   # 取证截图随任务上传网页证据墙
    log(f"执行器 v{dex.EXEC_VERSION}（本体 v{AGENT_VERSION}）就位")
    log(dex.dpi_report())   # 一行体检：显示缩放没对齐这里立刻露馅，不用等点击歪了才发现
    log(dex.vis_report())   # 跨分辨率体检：这台机器"模型能不能看清界面"，换机前先看这行
    import pyperclip
    # 服务端从目标里识别的目标软件（如 WorkBuddy/豆包）——派哪个软件就指挥哪个软件
    app = str(job.get("app") or "").strip() or "豆包"
    log(f"接到任务「{job['name']}」（第 {job['attempt']} 次执行），开始指挥本机{app}……")
    q1 = (f"【总目标】{job['goal']}\n"
          f"请完成其中的子任务「{job['name']}」。\n"
          f"验收要求（必须满足）：{job['acceptance']}\n")
    if job.get("feedback"):
        q1 += f"监工意见（上一版被打回的原因，本次必须修正）：{job['feedback']}\n"
    resume = str(job.get("resume") or "").strip()
    if resume:
        q1 = (f"【接续说明】本任务是暂停后恢复的。暂停前的进度存档：{resume}\n"
              f"请从中断处继续，不要重开话题、不要重做已完成的部分。\n") + q1
    q1 += "信息不足之处请自行合理拟定（自拟主题/自选风格），直接给出完整交付内容，不要反问。"
    tag = time.strftime("local_%H%M%S")
    old_clip = ""
    try:
        old_clip = pyperclip.paste() or ""
    except Exception:
        pass
    deliver, err = "", ""
    try:
        # 开工前先把鼠标挪到屏幕中心: 无人值守/演示休息时鼠标常停在左上角,
        # 正落在 FAILSAFE 急停区, 第一轮操作就会触发急停(2026-11-05 测试机实测).
        try:
            _sw, _sh = pyautogui.size()
            pyautogui.moveTo(_sw // 2, _sh // 2, duration=0.6)
        except Exception:
            pass
        w = dex.find_window(app) or dex.launch(app)
        if not w:
            raise RuntimeError(
                f"本机没有打开「{app}」窗口，也未能自动启动（未找到安装位置）——"
                f"请先在本机手动打开{app}再重新派单，或换一个已安装的软件")
        w = dex.focus(w)   # focus 内部会按标题保鲜矩形，返回刷过的窗口对象
        # ---- 开屏感知（KB6）：先"看一眼"界面状态，再决定动作——不是流水线 ----
        # 弹窗挡路→先清；已在新空会话→免隔离直接干；其余→照旧开新对话隔离少爷的会话。
        # 感知失败(unknown/异常)一律回退原流程，知识库故障绝不挡执行。
        sense = {}
        try:
            sense = dex.sense_screen(w, app)
            log(f"开屏感知：{sense.get('state')}（{str(sense.get('note',''))[:48]}）")
            if sense.get('state') == 'dialog_popup':
                if dex.close_popup(w, app, hint=sense.get('question') or ''):
                    sense = dex.sense_screen(w, app)
                    log(f"弹窗已清，复感知：{sense.get('state')}")
        except Exception as e:
            log(f"开屏感知异常（{e}），按原流程走")
        if sense.get('state') == 'empty_chat':
            log("已在新空会话——免开新对话，直接开工")
        else:
            dex.new_chat(w, app)
        # ---- 复合接力（KB7）：云端标了 attachPrev → 把上一步产物落成本地文件喂进去 ----
        atext = str(job.get('attachText') or '')
        if atext:
            import tempfile
            try:
                fpath = os.path.join(tempfile.gettempdir(), f"guga_relay_{job['stId']}.txt")
                with open(fpath, 'w', encoding='utf-8') as f:
                    f.write(atext)
                ok_a, msg_a = dex.attach_file(w, app, fpath)
                log(f"接力喂文件：{'✅ ' if ok_a else '⚠️ '}{msg_a}")
                if not ok_a:
                    # 降级：喂不进去就把产物全文注入提问，活照样干，如实留痕
                    q1 = (f"【接力说明】文件喂入未成功，以下为上一步产物全文，请基于它继续：\n"
                          f"{atext[:4000]}\n\n") + q1
            except Exception as e:
                log(f"接力喂文件异常（{e}），降级为文本注入")
                q1 = f"【接力说明】以下为上一步产物全文，请基于它继续：\n{atext[:4000]}\n\n" + q1
        nxt, rounds = q1, 0
        last_reply = ""
        while rounds < 4:
            # 暂停检查点：少爷在网页按了暂停，本轮边界立刻收手上报进度（进度存档可无缝续跑）
            try:
                ctl = api("/api/agent/ctl", {"taskId": job["taskId"]}, token, timeout=15)
            except Exception:
                ctl = {}
            if ctl.get("action") == "pause":
                ctx = (f"已与{app}对话 {rounds} 轮"
                       + (f"，最后一轮回复开头：「{last_reply[:80]}」" if last_reply else "")
                       + f"；下一步：继续指挥{app}直至拿到满足验收标准的完整交付")
                api("/api/agent/paused", {"taskId": job["taskId"], "stId": job["stId"],
                                          "ctx": ctx}, token, timeout=15)
                log(f"少爷已暂停：进度已存档（{ctx}），收手待命")
                return
            rounds += 1
            ok, reply = dex.ask_round(w, nxt, old_clip, tag, rounds, app)
            last_reply = reply or last_reply
            if not ok:
                err = f"第 {rounds} 轮未能取到{app}回复（粘贴/超时/复制失败）"
                break
            try:
                c = api("/api/agent/consult", {
                    "taskId": job["taskId"], "stId": job["stId"],
                    "goal": job["goal"], "name": job["name"],
                    "acceptance": job["acceptance"], "reply": reply, "app": app,
                }, token, timeout=90)
            except Exception as e:
                log(f"大脑请示通道波动（{e}），按当前回复直接交付，由网页验收兜底")
                deliver = reply
                break
            if c.get("type") == "followup" and c.get("text"):
                log(f"大脑判定豆包在反问/未给正文，按大脑代拟的话继续追问：「{c['text'][:40]}…」")
                nxt = c["text"]
                continue
            log("大脑判定这是完整交付，回传网页验收")
            deliver = reply
            break
        else:
            err = "追问 4 轮仍未拿到完整交付"
        if deliver:
            r = api("/api/agent/result", {"taskId": job["taskId"], "stId": job["stId"],
                                          "ok": True, "content": deliver}, token)
            log(f"产物已回传（{len(deliver)} 字）。网页验收结果："
                + ("✅ 通过" if r.get("pass") else "❌ 被监工打回，稍后会领到返工单"))
        else:
            api("/api/agent/result", {"taskId": job["taskId"], "stId": job["stId"],
                                      "ok": False, "note": err[:200]}, token)
            log(f"未能拿到完整交付（{err}），已如实回报网页")
    except Exception as e:
        log(f"执行异常：{e}")
        try:
            api("/api/agent/result", {"taskId": job["taskId"], "stId": job["stId"],
                                      "ok": False, "note": str(e)[:200]}, token)
        except Exception:
            pass
    finally:
        dex.CTX = None
        try:
            pyperclip.copy(old_clip)   # 恢复剪贴板
        except Exception:
            pass


def _keepalive(token, stop):
    """干活期间的保活心跳：run_job 一跑十几分钟，主循环不拍心跳，
    服务端会把这台电脑误判成离线（另一端看到"没反应"）。busy=True 只报平安不领新单。"""
    while not stop.is_set():
        try:
            api("/api/agent/beat", {"path": HERE, "caps": local_caps(), "busy": True}, token, timeout=15)
        except Exception:
            pass
        stop.wait(4)


def main():
    # 环境守卫：本脚本是 Windows 程序。若被双击后由 WSL/Linux Python 接管（.py 关联被改），
    # 在这里拦下并给出中文指路，避免用户卡在 WSL 安装或莫名的报错里。
    if sys.platform.startswith('linux') or sys.platform == 'darwin':
        print("=" * 56)
        print("  [!] 检测到这是 Linux/macOS 环境 —— 咕嘎本体是 Windows 程序")
        print("  您可能是直接双击了 .py 文件（被系统用 WSL 打开了）。")
        print("  正确做法：关闭本窗口，回到 guga-desktop 文件夹，")
        print("  双击「2-启动咕嘎本体.bat」即可，无需敲任何命令。")
        print("=" * 56)
        try:
            input("按回车键退出……")
        except Exception:
            pass
        sys.exit(1)
    code = sys.argv[1] if len(sys.argv) > 1 else input("请输入网页上的 6 位配对码：").strip()
    if not code.isdigit():
        print("配对码应是 6 位数字（网页 🩺自检 → 生成配对码）")
        sys.exit(1)
    try:
        token = pair(code)
    except urllib.error.HTTPError as e:
        try:
            msg = json.loads(e.read().decode()).get("error", "配对失败")
        except Exception:
            msg = f"配对失败 HTTP {e.code}"
        print(msg)
        sys.exit(1)
    print("咕嘎本体开始值守：网页派「本机执行」的单会自动拉起本机 AI 干活")
    print("  · 任务进行中按 Ctrl+C = 打断当前任务（如实上报，值守继续）")
    print("  · 3 秒内连按两次 Ctrl+C 或空闲时按 Ctrl+C = 退出值守；鼠标甩到屏幕左上角 = 紧急停手")
    last_kb = 0.0
    while True:
        job = None
        try:
            b = api("/api/agent/beat", {"path": HERE, "caps": local_caps()}, token)
            job = b.get("job")
        except urllib.error.HTTPError as e:
            if e.code == 401:
                # 配对被顶替/失效不是"暂时不通"——明确告知并退出，不做无声僵尸
                print("本机执行方的配对已失效（同设备重新配对过，或绑定被清除）。")
                print("本进程退出。如需值守：重新双击咕嘎本体，输入网页上的新配对码即可。")
                sys.exit(0)
            log(f"心跳暂时不通（{e}），10 秒后重试")
            time.sleep(10)
            continue
        except Exception as e:
            log(f"心跳暂时不通（{e}），10 秒后重试")
            time.sleep(10)
            continue
        if job:
            keeper = threading.Event()
            threading.Thread(target=_keepalive, args=(token, keeper), daemon=True).start()
            try:
                run_job(job, token)
            except KeyboardInterrupt:
                # 少爷随时有权打断乱抢鼠标的本体：第一下只终结这一单，值守进程绝不能死
                #（否则远程显示"正在派单"而本机早已无人接单，两边都懵）
                if time.time() - last_kb < 5:
                    raise
                last_kb = time.time()
                log("任务已被少爷打断，如实上报后继续值守（3 秒内再按 Ctrl+C 才会退出）")
                try:
                    api("/api/agent/result", {"taskId": job["taskId"], "stId": job["stId"],
                                              "ok": False, "note": "少爷手动中断了本次执行"}, token)
                except Exception:
                    pass
                time.sleep(3)
            except Exception as e:
                # 任何任务级异常都只终结这一单：领单→干活→回报，心跳循环必须活着
                log(f"任务异常退出（{e!r}），已上报，值守继续")
                try:
                    api("/api/agent/result", {"taskId": job["taskId"], "stId": job["stId"],
                                              "ok": False, "note": f"执行异常：{e}"[:200]}, token)
                except Exception:
                    pass
            finally:
                keeper.set()   # 干完活停掉保活线程，主循环心跳接管
        time.sleep(4)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n值守已停止，少爷随时可以再启动。")
