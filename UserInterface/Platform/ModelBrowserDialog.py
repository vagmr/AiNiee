from typing import List
import re

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QListWidget, QListWidgetItem, QLabel

import httpx

from qfluentwidgets import MessageBoxBase, LineEdit, PushButton, StrongBodyLabel, FluentIcon

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
        self._fetch_models()

    # 公开方法：获取选择的模型
    def get_selected_models(self) -> List[str]:
        items = self.list_widget.selectedItems()
        return [i.text() for i in items]

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

        # 列表
        self.list_widget = QListWidget(self)
        self.list_widget.setSelectionMode(QListWidget.ExtendedSelection)
        self.list_widget.itemSelectionChanged.connect(self._on_selection_change)
        self.list_widget.itemDoubleClicked.connect(lambda _: self._accept_if_single_clicked())
        self.viewLayout.addWidget(self.list_widget)

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
        self.yesButton.setEnabled(len(self.list_widget.selectedItems()) > 0)

    def _accept_if_single_clicked(self) -> None:
        # 双击时，若只选中一个则直接确认
        if len(self.list_widget.selectedItems()) == 1:
            self.accept()

    # 数据刷新
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

        self.list_widget.clear()
        for m in self._filtered[start:end]:
            item = QListWidgetItem(m)
            self.list_widget.addItem(item)

