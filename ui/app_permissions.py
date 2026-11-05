"""Explicit application launch grants, editable by the human only."""
from PyQt5.QtWidgets import (QDialog, QVBoxLayout, QLabel, QListWidget, QPushButton,
    QHBoxLayout, QFileDialog, QInputDialog, QCheckBox)


class AppPermissionsDialog(QDialog):
    def __init__(self, apps, parent=None):
        super().__init__(parent)
        self.apps = apps
        self.setWindowTitle('咕嘎 · 软件权限')
        self.resize(560, 390)
        layout = QVBoxLayout(self)
        label = QLabel('完整访问：发现和打开本机软件、读写文件、执行限时命令，并通过已配置的 MCP 执行软件任务。\n实际系统权限继承咕嘎进程。关闭后仅能启动下方手动添加的软件。')
        label.setWordWrap(True)
        layout.addWidget(label)
        self.full_access=QCheckBox('允许咕嘎完整访问本机（包含修改自身源码）')
        self.full_access.setChecked(self.apps.access.enabled)
        self.full_access.toggled.connect(self.apps.access.set_enabled)
        layout.addWidget(self.full_access)
        self.list = QListWidget()
        layout.addWidget(self.list, 1)
        self.hint = QLabel('只授权你信任的软件或快捷方式。')
        self.hint.setWordWrap(True)
        layout.addWidget(self.hint)
        row = QHBoxLayout()
        add = QPushButton('添加软件…')
        add.clicked.connect(self.add)
        row.addWidget(add)
        remove = QPushButton('撤销授权')
        remove.clicked.connect(self.remove)
        row.addWidget(remove)
        done = QPushButton('完成')
        done.clicked.connect(self.accept)
        row.addWidget(done)
        layout.addLayout(row)
        self.refresh()

    def refresh(self):
        self.list.clear()
        for name, path in self.apps.entries().items():
            self.list.addItem(name)
            self.list.item(self.list.count() - 1).setToolTip(path)

    def add(self):
        path, _ = QFileDialog.getOpenFileName(self, '选择允许咕嘎打开的软件', '', '软件或快捷方式 (*.exe *.lnk)')
        if not path:
            return
        from pathlib import Path
        name, ok = QInputDialog.getText(self, '软件名称', '你说话时使用的名称，例如“记事本”', text=Path(path).stem)
        if ok:
            try:
                self.apps.grant(name, path)
                self.refresh()
            except Exception as exc:
                self.hint.setText(str(exc))

    def remove(self):
        if self.list.currentItem():
            self.apps.revoke(self.list.currentItem().text())
            self.refresh()
