from PyQt5.QtCore import Qt, QSize
from qfluentwidgets import SplashScreen as FluentSplashScreen


class SplashScreen(FluentSplashScreen):
    """
    启动页面
    """
    
    def __init__(self, parent=None):
        
        super().__init__(
            icon="Resource/logo.png",
            parent=parent,
            enableShadow=True
        )
        
        # 图片的大小
        self.setIconSize(QSize(1024, 512))
        
        
        self.setWindowFlags(Qt.FramelessWindowHint)
        
        self.resize(1024, 512)

        # 透明背景
        self.setAttribute(Qt.WA_TranslucentBackground)
