"""Explicit, offline-first decision workbench. Independent from speech/chat UI."""
import json

from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtWidgets import (QDialog, QFileDialog, QHBoxLayout, QLabel, QHeaderView,
                             QPlainTextEdit, QPushButton, QVBoxLayout, QTabWidget,
                             QWidget, QTableWidget, QTableWidgetItem)

from core.bg_agent import (DecisionEngine, ROOT, decision_is_current, load_config,
                           log_diagnostic, validate_snapshot)


class DecisionWorker(QThread):
    done = pyqtSignal(int, object)

    def __init__(self, engine, snapshot, use_model, generation, parent=None):
        super().__init__(parent)
        self.engine, self.snapshot = engine, snapshot
        self.use_model, self.generation = use_model, generation

    def run(self):
        try:
            result = self.engine.decide(self.snapshot, self.use_model)
        except Exception:
            result = {"status": "error", "explanation": "局面或决策处理失败，请检查输入格式"}
        if not self.isInterruptionRequested():
            self.done.emit(self.generation, result)


class BattlegroundAgentPanel(QDialog):
    speak_requested = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("咕嘎 · 战棋决策实验室")
        self.resize(980, 720)
        self.engine = DecisionEngine(load_config())
        self._generation = 0
        self._worker = None
        self._workers = []
        self._spoken_text = ""
        self.setStyleSheet("""
            QDialog { background:#111827; color:#e5e7eb; }
            QLabel { color:#d1d5db; font-size:13px; }
            QPushButton { background:#25324a; color:white; padding:9px 14px;
                          border:1px solid #42516b; border-radius:6px; }
            QPushButton:disabled { color:#64748b; }
            QPlainTextEdit { background:#0b1220; color:#d1e2ee; border:1px solid #344155;
                             border-radius:6px; font-family:Consolas; font-size:13px; }
            QTabWidget::pane { border:1px solid #344155; }
            QTabBar::tab { background:#1f2937; color:#94a3b8; padding:7px 16px; }
            QTabBar::tab:selected { background:#334155; color:white; }
            QTableWidget { background:#111c2f; color:#e2e8f0; gridline-color:#334155;
                           border:0; font-size:13px; }
            QHeaderView::section { background:#25324a; color:#cbd5e1; padding:6px; border:0; }
        """)
        layout = QVBoxLayout(self)
        title = QLabel("战棋决策实验室 · 算法候选 + 模型决策 + 结果校验")
        title.setStyleSheet("font-size:20px; font-weight:600; color:#93c5fd; padding:8px 0;")
        layout.addWidget(title)
        note = QLabel("当前阶段：离线教练。只生成下一步建议；特殊机制未完整实现，评分不是胜率。")
        note.setWordWrap(True)
        layout.addWidget(note)
        bar = QHBoxLayout()
        for text, callback in (("载入示例", self.load_demo), ("导入局面 JSON", self.import_snapshot),
                               ("检查日志数据", self.check_log)):
            button = QPushButton(text)
            button.clicked.connect(callback)
            bar.addWidget(button)
        layout.addLayout(bar)
        self.input = QPlainTextEdit()
        self.input.setPlaceholderText("导入结构化局面，或先载入示例。")
        self.input.textChanged.connect(self._invalidate)
        self.summary = QPlainTextEdit()
        self.summary.setReadOnly(True)
        self.input_tabs = QTabWidget()
        self.input_tabs.addTab(self.summary, "当前局面")
        self.input_tabs.addTab(self.input, "详细数据 / 编辑 JSON")
        layout.addWidget(self.input_tabs, 2)
        row = QHBoxLayout()
        self.local_button = QPushButton("本地算法分析 · 不调用 API")
        self.model_button = QPushButton("模型 + 算法分析 · 使用现有套餐额度")
        self.local_button.clicked.connect(lambda: self.analyze(False))
        self.model_button.clicked.connect(lambda: self.analyze(True))
        row.addWidget(self.local_button)
        row.addWidget(self.model_button)
        layout.addLayout(row)
        self.status = QLabel("等待局面")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.result_tabs = QTabWidget()
        recommendation = QWidget()
        result_layout = QVBoxLayout(recommendation)
        self.recommendation = QLabel("载入局面后，先点“本地算法分析”体验决策流程。")
        self.recommendation.setWordWrap(True)
        self.recommendation.setStyleSheet("color:#bfdbfe; font-size:15px; padding:8px;")
        result_layout.addWidget(self.recommendation)
        self.candidate_table = QTableWidget(0, 4)
        self.candidate_table.setHorizontalHeaderLabels(["动作", "对象", "算法评分", "依据"])
        self.candidate_table.setEditTriggers(QTableWidget.NoEditTriggers)
        self.candidate_table.verticalHeader().hide()
        header = self.candidate_table.horizontalHeader()
        for col in range(3):
            header.setSectionResizeMode(col, QHeaderView.ResizeToContents)
        header.setSectionResizeMode(3, QHeaderView.Stretch)
        result_layout.addWidget(self.candidate_table)
        self.speak_button = QPushButton("让咕嘎讲解这一步")
        self.speak_button.setEnabled(False)
        self.speak_button.setToolTip("从桌宠菜单打开时，可使用原来的普通语音播报")
        self.speak_button.clicked.connect(lambda: self.speak_requested.emit(self._spoken_text))
        result_layout.addWidget(self.speak_button)
        self.result_tabs.addTab(recommendation, "决策建议")
        self.output = QPlainTextEdit()
        self.output.setReadOnly(True)
        self.result_tabs.addTab(self.output, "结构化结果")
        layout.addWidget(self.result_tabs, 3)
        self.load_demo()

    def _invalidate(self):
        self._generation += 1
        self.status.setText("输入已变化，需要重新分析；旧建议已失效")
        self.output.clear()
        self.recommendation.setText("局面已变化，请重新分析。")
        self.candidate_table.setRowCount(0)
        self._spoken_text = ""
        self.speak_button.setEnabled(False)
        try:
            raw = json.loads(self.input.toPlainText())
            lines = [f"第 {raw.get('turn', '?')} 回合  ·  酒馆 {raw.get('tier', '?')} 级  ·  "
                     f"金币 {raw.get('gold', '?')}  ·  血量 {raw.get('health', '?')}"]
            for zone, label in (("board", "场上"), ("hand", "手牌"), ("shop", "商店"), ("choices", "待选择")):
                cards = raw.get(zone, [])
                if cards:
                    lines.append(label + "：" + "；".join(
                        f"{c.get('name', '?')} {c.get('attack', '?')}/{c.get('health', '?')}"
                        for c in cards if isinstance(c, dict)))
            self.summary.setPlainText("\n\n".join(lines))
        except (ValueError, TypeError, AttributeError):
            self.summary.setPlainText("局面数据尚未就绪，请检查详细数据。")

    def load_demo(self):
        self.input.setPlainText((ROOT / "data/bg_agent/demo.json").read_text(encoding="utf-8"))
        self.status.setText("已载入合成示例（不是实服卡牌或实战），可先使用本地算法")

    def import_snapshot(self):
        path, _ = QFileDialog.getOpenFileName(self, "导入局面", "", "JSON (*.json)")
        if not path:
            return
        try:
            from pathlib import Path
            if Path(path).stat().st_size > 100000:
                raise ValueError("文件超过 100 KB")
            text = Path(path).read_text(encoding="utf-8-sig")
            raw = json.loads(text)
            if isinstance(raw, dict) and "entities" in raw and "schema_version" not in raw:
                from core.bg_observation import normalize_tag_observation
                raw = normalize_tag_observation(raw)
                text = json.dumps(raw, ensure_ascii=False, indent=2)
            validate_snapshot(raw)
            self.input.setPlainText(text)
        except (OSError, ValueError) as exc:
            self.status.setText("导入失败：" + str(exc)[:160])

    def check_log(self):
        try:
            info = log_diagnostic()
            self._invalidate()
            self.output.setPlainText(json.dumps(info, ensure_ascii=False, indent=2))
            self.result_tabs.setCurrentIndex(1)
            self.status.setText("日志数据检查完成；缺失字段补齐前不生成实战动作")
        except Exception:
            self.status.setText("日志数据暂不可用")

    def analyze(self, use_model):
        if self._worker is not None and self._worker.isRunning():
            return
        try:
            snapshot = validate_snapshot(json.loads(self.input.toPlainText()))
        except (ValueError, TypeError) as exc:
            self.status.setText("局面格式错误：" + str(exc)[:160])
            return
        self._generation += 1
        self.engine.config = load_config()
        self.status.setText("正在分析…" + ("本次将发送面板内局面并消耗模型额度" if use_model else "本地运行"))
        self.local_button.setEnabled(False)
        self.model_button.setEnabled(False)
        worker = DecisionWorker(self.engine, snapshot, use_model, self._generation, self)
        worker.done.connect(self._on_result)
        worker.finished.connect(lambda w=worker: self._finished(w))
        self._worker = worker
        self._workers.append(worker)
        worker.start()

    def _finished(self, worker):
        if self._worker is worker:
            self._worker = None
        if worker in self._workers:
            self._workers.remove(worker)
        worker.deleteLater()
        self.local_button.setEnabled(True)
        self.model_button.setEnabled(True)

    def _on_result(self, generation, result):
        if generation != self._generation:
            return
        if result.get("action"):
            try:
                current = json.loads(self.input.toPlainText())
                if not decision_is_current(result, current):
                    self.status.setText("返回时局面已变化或过期，请重新分析")
                    return
            except ValueError:
                return
        self.output.setPlainText(json.dumps(result, ensure_ascii=False, indent=2))
        self.result_tabs.setCurrentIndex(0)
        source = {"local_heuristic": "本地算法", "configured_model": "模型 + 算法"}.get(result.get("source"), "决策")
        if result.get("status") == "blocked":
            self.status.setText("数据不足：" + result.get("explanation", ""))
            self.recommendation.setText(result.get("explanation", "数据不足"))
        else:
            action = result.get("action") or {}
            labels = {"BUY": "购买", "PLAY": "打出", "SELL": "出售", "REFRESH": "刷新商店",
                      "FREEZE": "冻结商店", "UPGRADE": "升级酒馆", "CHOOSE": "选择", "END": "暂不操作"}
            raw = json.loads(self.input.toPlainText())
            names = {c.get("entity_id"): c.get("name", "") for zone in ("board", "hand", "shop", "choices")
                     for c in raw.get(zone, [])}
            phrase = labels.get(action.get("kind"), "无动作") + " " + names.get(action.get("entity_id"), "")
            self.status.setText(source + (" · 模型未通过校验，已回退" if result.get("status") == "fallback" else " · 分析完成"))
            self._spoken_text = phrase.strip() + "。" + result.get("explanation", "")
            self.recommendation.setText("建议：" + self._spoken_text)
            self.speak_button.setEnabled(bool(action) and self.parent() is not None)
            rows = result.get("candidates", [])
            self.candidate_table.setRowCount(len(rows))
            for row, candidate in enumerate(rows):
                values = [labels.get(candidate["kind"], candidate["kind"]),
                          names.get(candidate.get("entity_id"), "—"),
                          str(candidate["score"]), candidate["reason"]]
                for col, value in enumerate(values):
                    self.candidate_table.setItem(row, col, QTableWidgetItem(value))
                if candidate["action_id"] == action.get("action_id"):
                    self.candidate_table.selectRow(row)

    def closeEvent(self, event):
        self._generation += 1
        for worker in self._workers:
            worker.requestInterruption()
        # Keep the dialog alive while the bounded network request finishes.
        # QDialog's default close hides it; WA_DeleteOnClose is intentionally unset.
        super().closeEvent(event)
