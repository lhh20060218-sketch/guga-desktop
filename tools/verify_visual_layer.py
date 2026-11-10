"""统一视觉层实测：真实弹窗识别/选择/关闭校验、分段耗时、两种窗口尺寸下的比例定位。

运行：python tools/verify_visual_layer.py            # 全部
      python tools/verify_visual_layer.py dialog     # 只测真实弹窗
      python tools/verify_visual_layer.py timing     # 只测分段耗时
      python tools/verify_visual_layer.py scaling    # 只测两种窗口尺寸
"""
import ctypes
from ctypes import wintypes
import json
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from core.computer_control import ComputerControl  # noqa: E402


def find_dialog(title):
    import win32gui
    found = []

    def visit(hwnd, _):
        try:
            if (win32gui.IsWindowVisible(hwnd) and win32gui.GetClassName(hwnd) == '#32770'
                    and win32gui.GetWindowText(hwnd) == title):
                found.append(hwnd)
        except Exception:
            pass
        return True

    win32gui.EnumWindows(visit, None)
    return found[0] if found else 0


def dialog_case():
    import win32gui
    title = '咕嘎视觉层测试-弹窗'
    script = ('Add-Type -AssemblyName System.Windows.Forms;'
              '[System.Windows.Forms.MessageBox]::Show("咕嘎视觉层测试：是否继续？",'
              '"' + title + '","YesNo","Question")')
    proc = subprocess.Popen(['powershell.exe', '-NoProfile', '-STA', '-Command', script],
                            creationflags=0x08000000)
    hwnd = 0
    deadline = time.time() + 20
    while time.time() < deadline and not hwnd:
        hwnd = find_dialog(title)
        time.sleep(.05)
    if not hwnd:
        print('DIALOG: FAIL 未出现真实弹窗')
        return False
    computer = ComputerControl()
    probe = computer.execute(dict(action='dialog', hwnd=hwnd))
    print('DIALOG 识别:', json.dumps(dict(title=probe.get('title'), texts=probe.get('texts'),
                                         options=probe.get('options'), timings=probe.get('timings'),
                                         elapsed_ms=probe.get('elapsed_ms')), ensure_ascii=False))
    options = probe.get('options') or []
    choice = next((item for item in options
                   if any(word in item.get('name', '') for word in ('否', 'No', '取消', 'Cancel'))), None)
    if not choice:
        print('DIALOG: FAIL 没有识别到“否/取消”选项，选项=', [item.get('name') for item in options])
        proc.kill()
        return False
    print('DIALOG 模型选择:', choice.get('name'), '（按任务语义选“否”，不随机点）')
    started = time.perf_counter()
    receipt = computer.execute(dict(action='uia', hwnd=hwnd, uia_ref=choice.get('ref'),
                                    uia_operation='invoke', expect_closed=True, verify_wait_ms=800))
    elapsed = int((time.perf_counter() - started) * 1000)
    print('DIALOG 执行+校验:', json.dumps(dict(verified=receipt.get('verification', {}).get('verified'),
                                          dialog_closed=receipt.get('verification', {}).get('dialog_closed'),
                                          changed_ratio=receipt.get('verification', {}).get('changed_ratio'),
                                          timings=receipt.get('verification', {}).get('timings'),
                                          elapsed_ms=elapsed), ensure_ascii=False))
    closed = bool(receipt.get('verification', {}).get('dialog_closed'))
    try: proc.wait(timeout=3)
    except Exception: proc.kill()
    ok = closed and not win32gui.IsWindowVisible(hwnd)
    print('DIALOG: %s（真实 #32770 弹窗，UIA 选项→模型选择→执行→关闭校验）' % ('PASS' if ok else 'FAIL'))
    return ok


def timing_case():
    import win32gui
    from core.window_inventory import list_windows
    windows = [item for item in list_windows('') if not item.get('minimized')
               and item.get('rect') and item['rect'][2] - item['rect'][0] > 400]
    preferred = [item for item in windows
                 if 'joycode' in (str(item.get('title')) + str(item.get('process_name'))).casefold()]
    if not windows:
        print('TIMING: FAIL 没有可测窗口')
        return False
    hwnd = int((preferred or windows)[0]['hwnd'])
    computer = ComputerControl()
    computer.execute(dict(action='focus', hwnd=hwnd))
    rows = []
    started = time.perf_counter()
    observed = computer.execute(dict(action='observe', hwnd=hwnd))
    rows.append(('observe', int((time.perf_counter() - started) * 1000), observed.get('timings')))
    started = time.perf_counter()
    whole = computer.execute(dict(action='ocr', hwnd=hwnd))
    rows.append(('ocr-整窗', int((time.perf_counter() - started) * 1000),
                 dict(words=len(whole.get('words') or []), timings=whole.get('timings'))))
    started = time.perf_counter()
    region = computer.execute(dict(action='ocr', hwnd=hwnd,
                                   region=dict(x=.45, y=.72, w=.55, h=.24)))
    rows.append(('ocr-裁剪', int((time.perf_counter() - started) * 1000),
                 dict(words=len(region.get('words') or []), timings=region.get('timings'))))
    started = time.perf_counter()
    located = computer.execute(dict(action='locate', hwnd=hwnd, query_text='qwen'))
    rows.append(('locate', int((time.perf_counter() - started) * 1000),
                 dict(source=located.get('source'), elapsed_ms=located.get('elapsed_ms'))))
    started = time.perf_counter()
    verified = computer.execute(dict(action='verify', hwnd=hwnd, wait_ms=900))
    rows.append(('verify-900ms', int((time.perf_counter() - started) * 1000),
                 verified.get('timings')))
    for name, elapsed, detail in rows:
        print('TIMING %-12s %5d ms  %s' % (name, elapsed, json.dumps(detail, ensure_ascii=False)))
    return True


def _find_notepad():
    import win32gui
    found = []

    def visit(hwnd, _):
        try:
            if win32gui.IsWindowVisible(hwnd) and win32gui.GetClassName(hwnd) == 'Notepad':
                found.append(hwnd)
        except Exception:
            pass
        return True

    win32gui.EnumWindows(visit, None)
    return found[0] if found else 0


def scaling_case():
    """同一比例坐标在两种窗口尺寸（等价于不同分辨率/缩放后的布局）命中同一输入区。"""
    import win32gui
    proc = subprocess.Popen(['notepad.exe'])
    hwnd = 0
    deadline = time.time() + 10
    while time.time() < deadline and not hwnd:
        hwnd = _find_notepad(); time.sleep(.05)
    if not hwnd:
        print('SCALING: FAIL 记事本未启动')
        proc.terminate()
        return False
    computer = ComputerControl()
    results = []
    point = dict(x=.5, y=.42)
    try:
        for index, (width, height) in enumerate(((900, 560), (1350, 840))):
            win32gui.SetWindowPos(hwnd, 0, 120, 120, width, height, 0x0004)
            time.sleep(.25)
            computer.execute(dict(action='focus', hwnd=hwnd))
            observed = computer.execute(dict(action='observe', hwnd=hwnd))
            rectangle = observed.get('desktop_rect') or []
            pixel = (round(rectangle[0] + point['x'] * (rectangle[2] - rectangle[0])),
                     round(rectangle[1] + point['y'] * (rectangle[3] - rectangle[1])))
            computer.execute(dict(action='click', hwnd=hwnd, observation_id=observed['observation_id'],
                                  coordinate_space='ratio', x=point['x'], y=point['y']))
            first = computer.execute(dict(action='observe', hwnd=hwnd))
            computer.execute(dict(action='hotkey', hwnd=hwnd, observation_id=first['observation_id'],
                                  keys='ctrl+a', verify=False))
            cleared = computer.execute(dict(action='observe', hwnd=hwnd))
            computer.execute(dict(action='hotkey', hwnd=hwnd, observation_id=cleared['observation_id'],
                                  keys='delete', verify=False))
            typed = computer.execute(dict(action='observe', hwnd=hwnd))
            needle = 'GUGAPROBE%d' % width
            computer.execute(dict(action='type', hwnd=hwnd, observation_id=typed['observation_id'],
                                  text=needle))
            check = computer.execute(dict(action='verify', hwnd=hwnd, expect_text='GUGAPROBE',
                                          region=dict(x=0, y=0, w=1, h=.8), wait_ms=900))
            results.append(dict(size=[width, height], rect=rectangle, ratio_point=point, pixel=pixel,
                                text_found=check.get('text_found'), verified=check.get('verified'),
                                verify_ms=check.get('elapsed_ms')))
            print('SCALING %dx%d rect=%s ratio=(%.2f,%.2f) pixel=%s text_found=%s verify_ms=%s'
                  % (width, height, rectangle, point['x'], point['y'], pixel,
                     check.get('text_found'), check.get('elapsed_ms')))
    finally:
        proc.terminate()
    ok = all(item.get('text_found') for item in results)
    print('SCALING: %s（同一比例坐标在两种窗口尺寸都命中同一输入区）' % ('PASS' if ok else 'FAIL'))
    return ok


def dpi_report():
    report = dict(system_dpi=96, process_dpi_awareness=None)
    try:
        if hasattr(ctypes.windll.user32, 'GetDpiForSystem'):
            report['system_dpi'] = int(ctypes.windll.user32.GetDpiForSystem())
    except Exception:
        pass
    try:
        awareness = ctypes.c_int(-1)
        result = ctypes.windll.shcore.GetProcessDpiAwareness(0, ctypes.byref(awareness))
        report['process_dpi_awareness'] = awareness.value if result == 0 else 'error:%s' % result
    except Exception:
        pass
    print('DPI:', json.dumps(report, ensure_ascii=False),
          '（0=unaware 1=system 2=per-monitor；动作执行时线程级 SetThreadDpiAwarenessContext(-4)）')
    return report


if __name__ == '__main__':
    which = sys.argv[1] if len(sys.argv) > 1 else 'all'
    ok = True
    dpi_report()
    if which in ('all', 'dialog'):
        ok = dialog_case() and ok
    if which in ('all', 'timing'):
        ok = timing_case() and ok
    if which in ('all', 'scaling'):
        ok = scaling_case() and ok
    print('RESULT:', 'PASS' if ok else 'FAIL')
