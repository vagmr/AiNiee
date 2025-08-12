from typing import List
import re

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QGridLayout

import httpx

from qfluentwidgets import (
    MessageBoxBase, LineEdit, PushButton, StrongBodyLabel, FluentIcon,
    PillPushButton, SingleDirectionScrollArea, isDarkTheme
)

from Base.Base import Base


class ModelBrowserDialog(MessageBoxBase, Base):
    """
    统一的“获取模型”对话框：
    - 支持从 OpenAI 兼容接口 GET /v1/models 拉取全部模型
    - 本地分页与搜索（适配几百条模型的展示）
    - 单/多选：按住 Ctrl/Shift 可多选；双击单条将立即确认
    """

    def __init__(self, window, platform_key: str, platform_config: dict):
        super().__init__(parent=window)
        self.platform_key = platform_key
        self.platform_config = platform_config

        # UI 基本设置
        self.widget.setMinimumSize(720, 520)
        self.yesButton.setText(self.tra("确定"))
        self.cancelButton.setText(self.tra("取消"))
        self.yesButton.setEnabled(False)

        # 数据
        self._all_models: List[str] = []
        self._filtered: List[str] = []
        self._page_size = 50
        self._current_page = 1

        # 构建界面
        self._build_ui()

        # 轻度样式优化
        self.setStyleSheet("""
        QListWidget { background: transparent; border: 1px solid rgba(255,255,255,0.08); }
        QListWidget::item { padding: 6px 10px; }
        QListWidget::item:selected { background: rgba(98, 160, 234, 0.18); border: none; }
        QLabel { color: palette(window-text); }
        """)

        # 异步/同步拉取数据（这里用同步 httpx，数据量一般可接受）
        # 容器背景使用主题色；按钮与主题色形成明暗对比，文本固定为 #f1356d
        theme_hex = None
        # 根据主题构造对比用的明暗色（覆盖在主题背景上）
        if isDarkTheme():
            theme_hex = "#2b2b2b"
            btn_bg = "#dddddd"
            btn_border = "rgba(255,255,255,0.28)"
            btn_hover = "rgba(255,255,255,0.22)"
            btn_checked = "rgba(255,255,255,0.30)"
        else:
            theme_hex = "#ffffff"
            btn_bg = "rgba(0,0,0,0.06)"
            btn_border = "rgba(0,0,0,0.18)"
            btn_hover = "rgba(0,0,0,0.10)"
            btn_checked = "rgba(0,0,0,0.16)"

        

        # 设置模型区域背景为主题色
        # 放在 grid_parent 上，使视觉上“模型展示区域”整体统一
        # 注意：为了有留白，外层布局已有边距
        self.grid_parent.setStyleSheet(f"QWidget {{ background-color: {theme_hex}; border-radius: 8px; }}")

        text_color = "#f1356d"  # 固定按钮文本色

        # 胶囊按钮样式
        self._capsule_style = (
            "QPushButton {"
            " border-radius: 18px; padding: 8px 14px;"
            f" border: 1px solid {btn_border};"
            f" background-color: {btn_bg};"
            f" color: {text_color};"
            "}"
            "QPushButton:hover {"
            f" background-color: {btn_hover};"
            "}"
            "QPushButton:checked {"
            f" background-color: {btn_checked};"
            f" border: 1px solid {btn_border};"
            f" color: {text_color};"
            "}"
        )

        self._fetch_models()

    # 公开方法：获取选择的模型
    def get_selected_models(self) -> List[str]:
        return list(self._selected)

    # UI
    def _build_ui(self) -> None:
        self.viewLayout.setContentsMargins(16, 16, 16, 16)

        # 标题
        title = StrongBodyLabel(self.tra("获取模型"), self)
        self.viewLayout.addWidget(title)

        # 搜索条
        top_bar = QHBoxLayout()
        self.search_box = LineEdit(self)
        self.search_box.setPlaceholderText(self.tra("搜索模型..."))
        self.search_box.textChanged.connect(self._on_search_changed)
        top_bar.addWidget(self.search_box, 1)

        # 分页控制
        self.prev_btn = PushButton(self.tra("上一页"), self)
        self.prev_btn.setIcon(FluentIcon.LEFT_ARROW)
        self.prev_btn.clicked.connect(lambda: self._goto_page(self._current_page - 1))
        self.next_btn = PushButton(self.tra("下一页"), self)
        self.next_btn.setIcon(FluentIcon.RIGHT_ARROW)
        self.next_btn.clicked.connect(lambda: self._goto_page(self._current_page + 1))
        self.page_label = QLabel("1/1", self)
        self.page_label.setAlignment(Qt.AlignCenter)

        top_bar.addWidget(self.prev_btn)
        top_bar.addWidget(self.page_label)
        top_bar.addWidget(self.next_btn)
        self.viewLayout.addLayout(top_bar)

        # 模型栅格（滚动区 + Grid）
        self.scroll_area = SingleDirectionScrollArea(self, orient=Qt.Vertical)
        self.scroll_area.setWidgetResizable(True)
        self.scroll_area.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        self.grid_parent = QWidget(self)
        self.grid_layout = QGridLayout(self.grid_parent)
        self.grid_layout.setContentsMargins(4, 8, 4, 8)
        self.grid_layout.setHorizontalSpacing(16)
        self.grid_layout.setVerticalSpacing(10)
        self.scroll_area.setWidget(self.grid_parent)
        self.viewLayout.addWidget(self.scroll_area)

        # 选择集合（跨页保留）
        self._selected = set()

    # 拉取模型
    def _fetch_models(self) -> None:
        base_url = self.platform_config.get("api_url", "").rstrip("/")
        auto_complete = self.platform_config.get("auto_complete", False)

        # 自动补全规则（参考 TranslatorConfig）
        if self.platform_key == "sakura" and not base_url.endswith("/v1"):
            base_url = base_url + "/v1"
        elif auto_complete and not re.search(r"/v[1-9]$", base_url):
            base_url = base_url + "/v1"

        url = f"{base_url}/models"

        # 处理鉴权与代理
        headers = {}
        api_keys = self.platform_config.get("api_key", "").replace(" ", "")
        if api_keys:
            headers["Authorization"] = f"Bearer {api_keys.split(',')[0]}"


        try:
            with httpx.Client(http2=True, timeout=30) as client:
                resp = client.get(url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
        except Exception as e:
            self.error_toast("", self.tra("获取模型失败"))
            self.debug(f"fetch models error: {e}")
            data = {}

        models = []
        # 兼容常见返回结构
        try:
            if isinstance(data, dict) and isinstance(data.get("data"), list):
                for item in data.get("data", []):
                    mid = item.get("id") or item.get("model")
                    if mid:
                        models.append(str(mid))
            elif isinstance(data, list):
                for item in data:
                    if isinstance(item, str):
                        models.append(item)
                    elif isinstance(item, dict):
                        mid = item.get("id") or item.get("model")
                        if mid:
                            models.append(str(mid))
        except Exception:
            pass

        # 去重并排序
        unique = sorted(list(dict.fromkeys(models)))
        self._all_models = unique
        self._apply_filter_and_refresh()

    # 事件
    def _on_search_changed(self, text: str) -> None:
        self._apply_filter_and_refresh()

    def _on_selection_change(self) -> None:
        # grid 方案改为使用内部集合控制按钮状态
        self.yesButton.setEnabled(len(self._selected) > 0)

    def _accept_if_single_clicked(self) -> None:
        # grid 方案：如果只有一个选择，仍然允许回车确认
        if len(self._selected) == 1:
            self.accept()

    # 数据刷新
    def _toggle_selection(self, name: str, checked: bool) -> None:
        if checked:
            self._selected.add(name)
        else:
            self._selected.discard(name)
        self._on_selection_change()

    def _apply_filter_and_refresh(self) -> None:
        q = self.search_box.text().strip().lower()
        if q:
            self._filtered = [m for m in self._all_models if q in m.lower()]
        else:
            self._filtered = list(self._all_models)
        self._current_page = 1
        self._refresh_list()

    def _goto_page(self, page: int) -> None:
        total_pages = max(1, (len(self._filtered) + self._page_size - 1) // self._page_size)
        page = max(1, min(page, total_pages))
        if page != self._current_page:
            self._current_page = page
            self._refresh_list()

    def _refresh_list(self) -> None:
        total = len(self._filtered)
        total_pages = max(1, (total + self._page_size - 1) // self._page_size)
        start = (self._current_page - 1) * self._page_size
        end = min(start + self._page_size, total)
        self.page_label.setText(f"{self._current_page}/{total_pages}")
        self.prev_btn.setEnabled(self._current_page > 1)
        self.next_btn.setEnabled(self._current_page < total_pages)

        # 清空旧的按钮
        while self.grid_layout.count():
            item = self.grid_layout.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        # 两列胶囊按钮布局
        cols = 2
        row = 0
        col = 0
        for m in self._filtered[start:end]:
            btn = PillPushButton(m, self.grid_parent)
            btn.setCheckable(True)
            btn.setChecked(m in self._selected)
            btn.setStyleSheet(self._capsule_style)
            btn.setMinimumWidth(240)
            btn.setMinimumHeight(36)
            btn.toggled.connect(lambda checked, name=m: self._toggle_selection(name, checked))
            self.grid_layout.addWidget(btn, row, col)
            col += 1
            if col >= cols:
                col = 0
                row += 1

