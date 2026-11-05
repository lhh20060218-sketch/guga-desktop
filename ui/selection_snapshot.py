"""Cache only the local region around a completed selection; no focus or clipboard."""
import ctypes
from ctypes import wintypes
from PyQt5.QtCore import QRect,QPoint
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QCursor


class MonitorInfo(ctypes.Structure):
    _fields_=[('size',wintypes.DWORD),('monitor',wintypes.RECT),('work',wintypes.RECT),
              ('flags',wintypes.DWORD),('device',wintypes.WCHAR*32)]


def snapshot(event):
    user=ctypes.windll.user32
    x,y=int(event.get('x',0)),int(event.get('y',0))
    user.MonitorFromPoint.argtypes=[wintypes.POINT,wintypes.DWORD];user.MonitorFromPoint.restype=wintypes.HANDLE
    user.GetMonitorInfoW.argtypes=[wintypes.HANDLE,ctypes.POINTER(MonitorInfo)]
    info=MonitorInfo();info.size=ctypes.sizeof(info)
    monitor=user.MonitorFromPoint(wintypes.POINT(x,y),2)
    if not monitor or not user.GetMonitorInfoW(monitor,ctypes.byref(info)):raise RuntimeError('无法定位选区所在显示器')
    screens=QApplication.screens()
    screen=next((s for s in screens if s.name().upper()==info.device.upper()),None)
    screen=screen or QApplication.screenAt(QCursor.pos()) or QApplication.primaryScreen()
    bounds=screen.geometry();native=info.monitor
    rx=bounds.width()/max(1,native.right-native.left);ry=bounds.height()/max(1,native.bottom-native.top)
    def point(px,py):return QPoint(round(bounds.left()+(px-native.left)*rx),round(bounds.top()+(py-native.top)*ry))
    end=point(x,y);start=point(event.get('start_x',x),event.get('start_y',y))
    extent=QRect(start,end).normalized();width=max(560,extent.width()+180);height=max(170,extent.height()+100)
    if extent.height()>24:width=max(width,900)
    width=min(width,bounds.width());height=min(height,700,bounds.height())
    rect=QRect(extent.center().x()-width//2,extent.center().y()-height//2,width,height)
    rect.moveLeft(max(bounds.left(),min(rect.left(),bounds.right()-width+1)))
    rect.moveTop(max(bounds.top(),min(rect.top(),bounds.bottom()-height+1)))
    # Clip neighboring applications out when the source frame is available.
    hwnd=event.get('hwnd',0);frame=wintypes.RECT();origin=wintypes.POINT()
    user.GetClientRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
    user.ClientToScreen.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.POINT)]
    if hwnd and user.GetClientRect(hwnd,ctypes.byref(frame)) and user.ClientToScreen(hwnd,ctypes.byref(origin)):
        source=QRect(point(origin.x,origin.y),point(origin.x+frame.right-1,origin.y+frame.bottom-1))
        rect=rect.intersected(source)
    if rect.width()<20 or rect.height()<20:raise RuntimeError('选区画面太小，请重新拖选文字')
    entire=screen.grabWindow(0)
    if entire.isNull():raise RuntimeError('无法读取选词时的画面')
    px=entire.width()/bounds.width();py=entire.height()/bounds.height()
    crop=entire.copy(round((rect.left()-bounds.left())*px),round((rect.top()-bounds.top())*py),round(rect.width()*px),round(rect.height()*py))
    if crop.isNull():raise RuntimeError('选区画面为空')
    # Supply a close-up of the actual drag line as well as paragraph context.
    # It prevents a model treating neighboring, unselected words as the target.
    focus=extent.adjusted(-5,-24,5,24)
    if extent.width()<8:focus=QRect(end.x()-120,end.y()-25,240,50)
    elif extent.height()>24:focus=QRect(rect.left(),extent.top()-18,rect.width(),extent.height()+36)
    focus=focus.intersected(rect)
    detail=entire.copy(round((focus.left()-bounds.left())*px),round((focus.top()-bounds.top())*py),max(1,round(focus.width()*px)),max(1,round(focus.height()*py)))
    return crop,end,detail
