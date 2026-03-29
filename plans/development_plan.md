# 漫画软件开发计划

## 一、技术选型

### 1.1 推荐方案：Python + PyQt6

| 维度 | 选择 | 理由 |
|------|------|------|
| **编程语言** | Python 3.11+ | 语法简洁、开发效率高、生态丰富、新手友好 |
| **GUI 框架** | PyQt6 | 功能强大、性能优秀、组件丰富、文档完善 |
| **数据库** | SQLite | Python 内置、无需安装、单文件易备份 |
| **配置存储** | JSON | 简单直观、易于手动编辑 |
| **图片处理** | Pillow + QImage | 支持多种格式、可高效处理大图 |
| **搜索** | SQLite FTS5 | 原生全文搜索、速度快、无需额外依赖 |

### 1.2 依赖包清单

```
PyQt6>=6.4.0          # GUI 框架
Pillow>=10.0.0        # 图片处理
watchdog>=3.0.0       # 文件系统监控（可选）
```

---

## 二、软件架构设计

### 2.1 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                      表现层 (UI Layer)                       │
│  ┌──────────┐  ┌──────────┐  ┌──────────┐  ┌──────────┐     │
│  │ 主窗口   │  │ 导入对话框│  │ 阅读器   │  │ 设置面板 │     │
│  │ (书架)   │  │          │  │          │  │          │     │
│  └────┬─────┘  └────┬─────┘  └────┬─────┘  └────┬─────┘     │
└───────┼─────────────┼─────────────┼─────────────┼───────────┘
        │             │             │             │
        └─────────────┴──────┬──────┴─────────────┘
                             │
┌────────────────────────────┼────────────────────────────────┐
│              业务逻辑层 (Service Layer)                      │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐         │
│  │ 漫画管理服务 │ │ 导入服务     │ │ 阅读记录服务 │         │
│  └──────────────┘ └──────────────┘ └──────────────┘         │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────┐         │
│  │ 搜索服务     │ │ 分组服务     │ │ 封面服务     │         │
│  └──────────────┘ └──────────────┘ └──────────────┘         │
└────────────────────────────┬────────────────────────────────┘
                             │
        ┌────────────────────┼────────────────────┐
        │                    │                    │
┌───────▼────────┐  ┌────────▼─────────┐  ┌──────▼──────┐
│  数据库层      │  │  配置层          │  │  文件层     │
│  (SQLite)      │  │  (JSON)          │  │  (本地文件) │
│                │  │                  │  │             │
│  - 漫画元数据  │  │  - 用户设置      │  │  - 原图     │
│  - 阅读进度    │  │  - 导入配置      │  │  - 缩略图   │
│  - 分组信息    │  │  - 快捷键配置    │  │  - 数据副本 │
└────────────────┘  └──────────────────┘  └─────────────┘
```

### 2.2 模块职责

| 模块 | 职责 |
|------|------|
| **MainWindow** | 主窗口管理，页面切换协调 |
| **LibraryView** | 书架展示，网格/列表布局 |
| **ImportDialog** | 导入向导，元数据编辑 |
| **ReaderWindow** | 阅读器，图片显示与导航 |
| **MangaService** | 漫画 CRUD，自动合并逻辑 |
| **ImportService** | 文件夹扫描，图片导入处理 |
| **ReaderService** | 阅读状态管理，进度保存 |
| **SearchService** | 全文搜索，快速查找 |
| **Database** | SQLite 操作，数据持久化 |
| **ImageLoader** | 图片异步加载，预加载管理 |
| **ThumbnailCache** | 缩略图生成与缓存 |

---

## 三、数据模型设计

### 3.1 数据库表结构 (SQLite)

```sql
-- 漫画系列表
CREATE TABLE series (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,                    -- 漫画名称
    author TEXT,                           -- 作者
    total_episodes INTEGER DEFAULT 1,      -- 总集数
    cover_path TEXT,                       -- 封面图片路径
    is_favorite BOOLEAN DEFAULT 0,         -- 是否收藏
    tags TEXT,                             -- 标签，JSON 数组存储
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 集数表
CREATE TABLE episodes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id INTEGER NOT NULL,
    episode_number INTEGER NOT NULL,       -- 第几集
    title TEXT,                            -- 集标题（可选）
    folder_path TEXT NOT NULL,             -- 原文件夹路径
    storage_mode TEXT DEFAULT 'reference', -- 'reference'=索引, 'copy'=复制
    data_path TEXT,                        -- 复制模式下的存储路径
    image_count INTEGER DEFAULT 0,         -- 图片数量
    is_read BOOLEAN DEFAULT 0,             -- 是否已读
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (series_id) REFERENCES series(id),
    UNIQUE(series_id, episode_number)
);

-- 图片表
CREATE TABLE images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    episode_id INTEGER NOT NULL,
    file_name TEXT NOT NULL,               -- 文件名
    file_path TEXT NOT NULL,               -- 完整路径
    file_size INTEGER,                     -- 文件大小
    sort_order INTEGER NOT NULL,           -- 排序序号
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (episode_id) REFERENCES episodes(id)
);

-- 阅读进度表
CREATE TABLE reading_progress (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    series_id INTEGER NOT NULL UNIQUE,     -- 每个漫画一条记录
    current_episode_id INTEGER NOT NULL,
    current_image_id INTEGER NOT NULL,
    last_read_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (series_id) REFERENCES series(id),
    FOREIGN KEY (current_episode_id) REFERENCES episodes(id),
    FOREIGN KEY (current_image_id) REFERENCES images(id)
);

-- 用户分组表
CREATE TABLE user_groups (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    sort_order INTEGER DEFAULT 0,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- 分组与漫画关联表
CREATE TABLE series_groups (
    series_id INTEGER NOT NULL,
    group_id INTEGER NOT NULL,
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (series_id, group_id),
    FOREIGN KEY (series_id) REFERENCES series(id),
    FOREIGN KEY (group_id) REFERENCES user_groups(id)
);

-- 创建全文搜索索引
CREATE VIRTUAL TABLE series_fts USING fts5(
    name, author, tags,
    content='series',
    content_rowid='id'
);
```

### 3.2 JSON 配置结构

```json
{
  "app": {
    "version": "1.0.0",
    "data_directory": "./data",
    "theme": "default"
  },
  "import": {
    "default_storage_mode": "reference",
    "auto_extract_cover": true,
    "cover_source": "first_image"
  },
  "reader": {
    "default_zoom": "fit_to_screen",
    "zoom_levels": [25, 50, 75, 100, 125, 150, 200],
    "preload_count": 2,
    "key_bindings": {
      "next_image": ["Right", "Space"],
      "prev_image": ["Left"],
      "next_episode": ["Page_Down"],
      "prev_episode": ["Page_Up"],
      "toggle_fullscreen": ["F11"],
      "exit_reader": ["Escape"]
    }
  },
  "library": {
    "cover_size": "medium",
    "sort_by": "updated_at",
    "sort_order": "desc"
  },
  "theme": {
    "current": "default",
    "follow_system": false,
    "custom_themes": [],
    "presets": {
      "default": {
        "name": "默认主题",
        "description": "经典浅色主题",
        "colors": {
          "primary": "#2196F3",
          "secondary": "#FFC107",
          "background": "#FFFFFF",
          "surface": "#F5F5F5",
          "text_primary": "#212121",
          "text_secondary": "#757575",
          "border": "#E0E0E0",
          "accent": "#FF5722"
        },
        "reader": {
          "background": "#1A1A1A",
          "page_spacing": 20,
          "scrollbar_style": "default"
        }
      },
      "dark": {
        "name": "深色主题",
        "description": "夜间阅读模式",
        "colors": {
          "primary": "#90CAF9",
          "secondary": "#FFE082",
          "background": "#121212",
          "surface": "#1E1E1E",
          "text_primary": "#FFFFFF",
          "text_secondary": "#B0B0B0",
          "border": "#333333",
          "accent": "#FF8A65"
        },
        "reader": {
          "background": "#000000",
          "page_spacing": 20,
          "scrollbar_style": "dark"
        }
      },
      "eye_care": {
        "name": "护眼模式",
        "description": "暖色调，适合长时间阅读",
        "colors": {
          "primary": "#8D6E63",
          "secondary": "#A1887F",
          "background": "#F5E6D3",
          "surface": "#E8D5C4",
          "text_primary": "#3E2723",
          "text_secondary": "#5D4037",
          "border": "#D7CCC8",
          "accent": "#6D4C41"
        },
        "reader": {
          "background": "#2C2416",
          "page_spacing": 20,
          "scrollbar_style": "warm"
        }
      },
      "modern": {
        "name": "现代简约",
        "description": "扁平化设计风格",
        "colors": {
          "primary": "#6200EE",
          "secondary": "#03DAC6",
          "background": "#FAFAFA",
          "surface": "#FFFFFF",
          "text_primary": "#000000",
          "text_secondary": "#666666",
          "border": "#EEEEEE",
          "accent": "#B00020"
        },
        "reader": {
          "background": "#121212",
          "page_spacing": 16,
          "scrollbar_style": "minimal"
        }
      },
      "sakura": {
        "name": "樱花粉",
        "description": "粉色系温馨主题",
        "colors": {
          "primary": "#EC407A",
          "secondary": "#F48FB1",
          "background": "#FFF0F5",
          "surface": "#FCE4EC",
          "text_primary": "#880E4F",
          "text_secondary": "#C2185B",
          "border": "#F8BBD9",
          "accent": "#D81B60"
        },
        "reader": {
          "background": "#2D1F24",
          "page_spacing": 20,
          "scrollbar_style": "pink"
        }
      }
    }
  }
}
```

### 3.3 主题系统设计

#### 3.3.1 主题系统架构

```
┌─────────────────────────────────────────────────────────────┐
│                      主题管理系统                             │
│                                                             │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐         │
│  │ 预设主题库   │  │ 自定义主题   │  │ 系统主题检测 │         │
│  │             │  │             │  │             │         │
│  │ - default   │  │ - 用户创建   │  │ - 跟随系统   │         │
│  │ - dark      │  │ - 导入导出   │  │ - 自动切换   │         │
│  │ - eye_care  │  │ - 分享功能   │  │             │         │
│  │ - modern    │  │             │  │             │         │
│  │ - sakura    │  │             │  │             │         │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘         │
│         │                │                │                │
│         └────────────────┴────────────────┘                │
│                          │                                  │
│                   ┌──────▼──────┐                          │
│                   │  主题引擎    │                          │
│                   │             │                          │
│                   │ - 颜色管理   │                          │
│                   │ - 样式生成   │                          │
│                   │ - 动态应用   │                          │
│                   │ - 过渡动画   │                          │
│                   └──────┬──────┘                          │
│                          │                                  │
│         ┌────────────────┼────────────────┐                │
│         │                │                │                │
│    ┌────▼────┐     ┌────▼────┐     ┌────▼────┐            │
│    │ UI 组件  │     │ 阅读器   │     │ 设置面板 │            │
│    │ 样式更新 │     │ 主题适配 │     │ 主题选择 │            │
│    └─────────┘     └─────────┘     └─────────┘            │
└─────────────────────────────────────────────────────────────┘
```

#### 3.3.2 主题配置界面设计

**设置面板 - 主题标签页：**

```
┌──────────────────────────────────────────────────────────────┐
│  主题设置                                        [预览] [应用]│
├──────────────────────────────────────────────────────────────┤
│                                                              │
│  当前主题                                                    │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  [跟随系统 ▼]  跟随 Windows/macOS 系统主题设置          ││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
│  预设主题                                                    │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐        ││
│  │  │ 🌞     │  │ 🌙     │  │ 👁️     │  │ ✨     │        ││
│  │  │ 默认   │  │ 深色   │  │ 护眼   │  │ 现代   │        ││
│  │  │ 选中 ✓ │  │        │  │        │  │        │        ││
│  │  └────────┘  └────────┘  └────────┘  └────────┘        ││
│  │  ┌────────┐  ┌────────┐  ┌────────┐  ┌────────┐        ││
│  │  │ 🌸     │  │ ➕     │  │        │  │        │        ││
│  │  │ 樱花   │  │ 添加   │  │        │  │        │        ││
│  │  │        │  │ 自定义 │  │        │  │        │        ││
│  │  └────────┘  └────────┘  └────────┘  └────────┘        ││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
│  [自定义主题列表...]                                         │
│                                                              │
│  颜色配置（仅自定义主题可编辑）                              │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  主色调      [████ #2196F3]  [选择颜色 ▼]               ││
│  │  强调色      [████ #FFC107]  [选择颜色 ▼]               ││
│  │  背景色      [████ #FFFFFF]  [选择颜色 ▼]               ││
│  │  文字主色    [████ #212121]  [选择颜色 ▼]               ││
│  │  文字次色    [████ #757575]  [选择颜色 ▼]               ││
│  │  边框色      [████ #E0E0E0]  [选择颜色 ▼]               ││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
│  阅读器配置                                                  │
│  ┌─────────────────────────────────────────────────────────┐│
│  │  背景颜色    [████ #1A1A1A]  [选择颜色 ▼]               ││
│  │  页边距      [━━━●━━━━] 20px                           ││
│  │  滚动条样式  [默认 ▼]                                   ││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
│  [导出主题]  [导入主题]  [恢复默认]                          │
│                                                              │
└──────────────────────────────────────────────────────────────┘
```

#### 3.3.3 主题管理类设计

```python
class ThemeManager:
    """主题管理器 - 负责主题的加载、应用和切换"""
    
    def __init__(self):
        self.current_theme = None
        self.presets = {}
        self.custom_themes = []
        self.follow_system = False
        self._load_themes()
        self._setup_system_listener()
    
    def _load_themes(self):
        """加载预设和自定义主题"""
        # 加载内置预设主题
        self.presets = self._load_builtin_presets()
        # 加载用户自定义主题
        self.custom_themes = self._load_custom_themes()
    
    def apply_theme(self, theme_id: str):
        """应用指定主题"""
        theme = self._get_theme(theme_id)
        if theme:
            self.current_theme = theme
            self._generate_stylesheet(theme)
            self._apply_to_widgets(theme)
            self._save_current_theme(theme_id)
    
    def create_custom_theme(self, name: str, base_theme: str = None) -> dict:
        """创建新的自定义主题"""
        base = self._get_theme(base_theme) if base_theme else self.presets['default']
        custom_theme = {
            'id': f'custom_{uuid.uuid4().hex[:8]}',
            'name': name,
            'colors': copy.deepcopy(base['colors']),
            'reader': copy.deepcopy(base['reader']),
            'is_custom': True
        }
        self.custom_themes.append(custom_theme)
        self._save_custom_themes()
        return custom_theme
    
    def update_theme_color(self, theme_id: str, color_key: str, color_value: str):
        """更新主题颜色"""
        theme = self._get_theme(theme_id)
        if theme and theme.get('is_custom'):
            theme['colors'][color_key] = color_value
            self._save_custom_themes()
            if self.current_theme.get('id') == theme_id:
                self.apply_theme(theme_id)
    
    def export_theme(self, theme_id: str, file_path: str):
        """导出主题到文件"""
        theme = self._get_theme(theme_id)
        if theme:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(theme, f, ensure_ascii=False, indent=2)
    
    def import_theme(self, file_path: str) -> dict:
        """从文件导入主题"""
        with open(file_path, 'r', encoding='utf-8') as f:
            theme = json.load(f)
            theme['id'] = f'custom_{uuid.uuid4().hex[:8]}'
            theme['is_custom'] = True
            self.custom_themes.append(theme)
            self._save_custom_themes()
            return theme
    
    def _setup_system_listener(self):
        """设置系统主题变化监听"""
        if sys.platform == 'win32':
            # Windows 注册表监听
            self._setup_windows_theme_listener()
        elif sys.platform == 'darwin':
            # macOS 通知监听
            self._setup_macos_theme_listener()
    
    def _on_system_theme_changed(self, is_dark: bool):
        """系统主题变化回调"""
        if self.follow_system:
            self.apply_theme('dark' if is_dark else 'default')


class ThemeStyleSheetGenerator:
    """样式表生成器 - 根据主题配置生成 QSS"""
    
    @staticmethod
    def generate_main_stylesheet(theme: dict) -> str:
        """生成主窗口样式表"""
        colors = theme['colors']
        return f"""
        QMainWindow {{
            background-color: {colors['background']};
        }}
        
        QWidget {{
            color: {colors['text_primary']};
            font-family: 'Microsoft YaHei', 'PingFang SC', sans-serif;
        }}
        
        QPushButton {{
            background-color: {colors['primary']};
            color: white;
            border: none;
            padding: 8px 16px;
            border-radius: 4px;
        }}
        
        QPushButton:hover {{
            background-color: {ThemeStyleSheetGenerator._lighten(colors['primary'])};
        }}
        
        QLineEdit, QTextEdit {{
            background-color: {colors['surface']};
            border: 1px solid {colors['border']};
            border-radius: 4px;
            padding: 6px;
        }}
        
        QScrollBar:vertical {{
            background-color: {colors['surface']};
            width: 12px;
            border-radius: 6px;
        }}
        
        QScrollBar::handle:vertical {{
            background-color: {colors['border']};
            border-radius: 6px;
            min-height: 20px;
        }}
        
        QListWidget, QTableWidget {{
            background-color: {colors['surface']};
            border: 1px solid {colors['border']};
            outline: none;
        }}
        
        QMenu {{
            background-color: {colors['surface']};
            border: 1px solid {colors['border']};
        }}
        
        QMenu::item:selected {{
            background-color: {colors['primary']};
            color: white;
        }}
        """
    
    @staticmethod
    def generate_reader_stylesheet(theme: dict) -> str:
        """生成阅读器样式表"""
        reader = theme['reader']
        return f"""
        ReaderWindow {{
            background-color: {reader['background']};
        }}
        
        #navigationBar {{
            background-color: rgba(0, 0, 0, 0.8);
            border-radius: 8px;
        }}
        
        #navigationBar QPushButton {{
            background-color: transparent;
            color: white;
            border: none;
            padding: 4px 8px;
        }}
        """
    
    @staticmethod
    def _lighten(color: str, amount: float = 0.2) -> str:
        """亮化颜色"""
        # 实现颜色亮化算法
        pass
```

#### 3.3.4 主题切换动画

```python
class ThemeTransitionManager:
    """主题过渡动画管理器"""
    
    def __init__(self, parent_widget: QWidget):
        self.parent = parent_widget
        self.overlay = QLabel(parent_widget)
        self.overlay.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.overlay.hide()
        
    def animate_transition(self, from_theme: dict, to_theme: dict, duration: int = 300):
        """执行主题切换动画"""
        # 创建渐变遮罩
        self.overlay.setGeometry(self.parent.rect())
        self.overlay.show()
        self.overlay.raise_()
        
        # 创建颜色过渡动画
        self.animation = QPropertyAnimation(self.overlay, b"windowOpacity")
        self.animation.setDuration(duration)
        self.animation.setStartValue(0.0)
        self.animation.setEndValue(1.0)
        self.animation.setEasingCurve(QEasingCurve.Type.InOutQuad)
        
        # 动画完成后切换主题
        self.animation.finished.connect(lambda: self._on_transition_complete(to_theme))
        self.animation.start()
    
    def _on_transition_complete(self, new_theme: dict):
        """过渡完成后应用新主题"""
        # 应用新主题
        ThemeManager().apply_theme_immediately(new_theme)
        # 淡出遮罩
        self.fade_out = QPropertyAnimation(self.overlay, b"windowOpacity")
        self.fade_out.setDuration(200)
        self.fade_out.setStartValue(1.0)
        self.fade_out.setEndValue(0.0)
        self.fade_out.finished.connect(self.overlay.hide)
        self.fade_out.start()
```

---

## 四、核心功能实现思路

### 4.1 导入功能

**流程：**
1. 用户选择文件夹"AAA"
2. 扫描文件夹内所有图片（支持格式：jpg, png, webp, bmp, gif）
3. 按文件名排序，计算图片数量
4. 弹出导入对话框，显示：
   - 名称（默认使用文件夹名）
   - 作者（默认为空）
   - 第几集（智能检测：如果名称包含"XXX第二集"，自动提取"2"）
   - 标签（多选输入）
   - 封面（可选：留空/使用某张图片/自动生成）
   - 存储模式（索引/复制）
5. 点击确认后：
   - 检查是否已存在同名漫画
   - 如存在同系列不同集数，自动合并更新 total_episodes
   - 如不存在，创建新系列
   - 保存图片信息到数据库
   - 如选择复制模式，复制图片到数据目录
   - 生成封面缩略图

**自动合并逻辑：**
```python
def import_episode(series_name, episode_number):
    existing = db.query("SELECT * FROM series WHERE name = ?", series_name)
    if existing:
        # 更新总集数
        new_total = max(existing.total_episodes, episode_number)
        db.execute("UPDATE series SET total_episodes = ? WHERE id = ?", 
                   new_total, existing.id)
        return existing.id
    else:
        # 创建新系列
        return create_new_series(series_name, episode_number)
```

### 4.2 书架功能

**界面布局：**
- 左侧边栏：分类导航
  - 全部漫画
  - 最喜欢 ★
  - 未读 ●
  - 已读 ✓
  - 自定义分组（可展开）
- 主区域：封面网格
  - 支持大/中/小三种封面尺寸
  - 显示漫画名称、当前集数/总集数
  - 未读显示标记
  - 右键菜单：阅读、编辑、删除、加入分组

**搜索功能：**
- 顶部搜索框，实时搜索
- 支持按名称、作者、标签搜索
- 使用 SQLite FTS5 实现毫秒级响应

### 4.3 阅读功能

**阅读器架构：**
```
┌─────────────────────────────────────────┐
│              阅读器窗口                  │
│  ┌─────────────────────────────────┐    │
│  │                                 │    │
│  │         图片显示区域             │    │
│  │      (QLabel + QPixmap)         │    │
│  │                                 │    │
│  └─────────────────────────────────┘    │
│  ┌─────────────────────────────────┐    │
│  │  [进度条] 第 X 集 / 共 Y 集     │    │
│  │  [←] [→]  1 / 20  [全屏] [设置] │    │
│  └─────────────────────────────────┘    │
└─────────────────────────────────────────┘
```

**图片加载与预加载：**
```python
class ImageLoader:
    def __init__(self):
        self.cache = LRUCache(maxsize=10)  # 缓存10张图片
        self.preload_thread = PreloadThread()
    
    def load_image(self, image_id):
        if image_id in self.cache:
            return self.cache[image_id]
        image = self._load_from_disk(image_id)
        self.cache[image_id] = image
        return image
    
    def preload(self, image_ids):
        # 后台线程预加载
        self.preload_thread.queue(image_ids)
```

**阅读逻辑：**
1. 打开漫画时，查询阅读进度
2. 如无记录，从第1集第1张开始
3. 有记录，恢复到最后阅读位置
4. 按键切换图片：
   - 右方向键/空格：下一张
   - 左方向键：上一张
   - PageDown：下一集
   - PageUp：上一集
5. 当前集读完时：
   - 自动标记该集为已读
   - 自动跳转到下一集第1张
   - 如没有下一集，提示"阅读完毕"
6. 每次切换图片，异步保存进度到数据库

**缩放功能：**
- 预设挡位：25%, 50%, 75%, 100%, 125%, 150%, 200%
- "适应屏幕"模式：等比缩放，完整显示图片
- "填充屏幕"模式：图片填满阅读区域（可能裁切）
- 支持鼠标滚轮缩放

---

## 五、项目目录结构

```
manga_reader/
├── main.py                      # 程序入口
├── requirements.txt             # 依赖清单
│
├── config/
│   ├── __init__.py
│   ├── settings.py              # 配置管理类
│   └── default_config.json      # 默认配置
│
├── core/
│   ├── __init__.py
│   ├── database.py              # SQLite 数据库操作
│   ├── models.py                # 数据模型类
│   ├── image_loader.py          # 图片加载与预加载
│   ├── thumbnail_cache.py       # 缩略图缓存
│   └── theme_manager.py         # 主题管理器
│
├── theme/
│   ├── __init__.py
│   ├── presets/                 # 预设主题
│   │   ├── default.json
│   │   ├── dark.json
│   │   ├── eye_care.json
│   │   ├── modern.json
│   │   └── sakura.json
│   ├── style_generator.py       # QSS 样式生成器
│   ├── transition_manager.py    # 主题切换动画
│   └── color_utils.py           # 颜色处理工具
│
├── services/
│   ├── __init__.py
│   ├── manga_service.py         # 漫画管理
│   ├── import_service.py        # 导入逻辑
│   ├── reader_service.py        # 阅读服务
│   ├── search_service.py        # 搜索服务
│   └── group_service.py         # 分组服务
│
├── ui/
│   ├── __init__.py
│   ├── main_window.py           # 主窗口
│   ├── library_view.py          # 书架视图
│   ├── import_dialog.py         # 导入对话框
│   ├── reader_window.py         # 阅读器窗口
│   ├── widgets/
│   │   ├── __init__.py
│   │   ├── cover_item.py        # 封面卡片
│   │   ├── image_viewer.py      # 图片显示组件
│   │   └── navigation_bar.py    # 导航栏
│   └── styles/
│       └── main.qss             # 样式文件
│
├── utils/
│   ├── __init__.py
│   ├── image_utils.py           # 图片处理工具
│   ├── file_utils.py            # 文件操作工具
│   └── validators.py            # 输入验证
│
└── data/                        # 数据目录（运行时创建）
    ├── manga_reader.db          # SQLite 数据库
    ├── config.json              # 用户配置
    ├── cache/                   # 缩略图缓存
    └── themes/                  # 用户主题存储
        ├── custom/              # 自定义主题
        └── exported/            # 导出的主题
```

---

## 六、开发阶段计划

### 阶段1：基础框架搭建

**目标：** 搭建项目结构，实现基础 UI 框架

**任务清单：**
- [ ] 创建项目目录结构
- [ ] 配置虚拟环境，安装依赖
- [ ] 实现配置管理类 (config/settings.py)
- [ ] 实现数据库基础类 (core/database.py)
- [ ] 创建数据模型 (core/models.py)
- [ ] 搭建主窗口框架 (ui/main_window.py)
- [ ] 实现左侧导航栏
- [ ] 实现基础样式

**验收标准：**
- 程序可以正常运行，显示主窗口
- 数据库可以创建表结构
- 配置可以读写

### 阶段2：导入功能开发

**目标：** 实现完整的导入流程

**任务清单：**
- [ ] 实现文件夹扫描功能
- [ ] 实现图片格式检测与排序
- [ ] 设计导入对话框 UI
- [ ] 实现元数据编辑界面
- [ ] 实现自动合并逻辑
- [ ] 实现封面选择功能
- [ ] 实现存储模式（索引/复制）
- [ ] 实现缩略图生成
- [ ] 编写导入服务层

**验收标准：**
- 可以导入文件夹并正确识别图片
- 可以编辑元数据并保存
- 自动合并逻辑正常工作
- 缩略图正确生成

### 阶段3：书架功能开发

**目标：** 实现书架展示与基本管理

**任务清单：**
- [ ] 实现封面卡片组件
- [ ] 实现网格布局书架
- [ ] 实现分类筛选（全部/最喜欢/未读/已读）
- [ ] 实现自定义分组功能
- [ ] 实现搜索功能（FTS5）
- [ ] 实现右键菜单
- [ ] 实现漫画编辑功能
- [ ] 实现删除功能

**验收标准：**
- 书架可以显示漫画封面
- 筛选和搜索功能正常
- 可以创建和管理分组
- 可以编辑和删除漫画

### 阶段4：阅读功能开发

**目标：** 实现完整的阅读体验

**任务清单：**
- [ ] 实现阅读器窗口
- [ ] 实现图片显示组件（支持缩放）
- [ ] 实现图片切换逻辑
- [ ] 实现预加载机制
- [ ] 实现阅读进度保存/恢复
- [ ] 实现自动跳转下一集
- [ ] 实现缩放功能（预设挡位 + 适应屏幕）
- [ ] 实现快捷键系统
- [ ] 实现阅读器设置面板

**验收标准：**
- 可以打开漫画并阅读
- 图片切换流畅（< 0.15s）
- 进度正确保存和恢复
- 自动跳转功能正常

### 阶段5：主题系统开发

**目标：** 实现完整的可自定义主题系统

**任务清单：**
- [ ] 实现主题管理器 (core/theme_manager.py)
- [ ] 实现样式生成器 (theme/style_generator.py)
- [ ] 实现颜色工具类 (theme/color_utils.py)
- [ ] 实现主题切换动画 (theme/transition_manager.py)
- [ ] 创建预设主题文件
  - [ ] default.json - 默认浅色主题
  - [ ] dark.json - 深色主题
  - [ ] eye_care.json - 护眼模式
  - [ ] modern.json - 现代简约
  - [ ] sakura.json - 樱花粉
- [ ] 实现主题设置面板 UI
  - [ ] 预设主题选择卡片
  - [ ] 颜色选择器组件
  - [ ] 实时预览功能
  - [ ] 导入/导出主题按钮
- [ ] 实现自定义主题 CRUD
  - [ ] 创建自定义主题
  - [ ] 编辑主题颜色
  - [ ] 删除自定义主题
- [ ] 实现系统主题跟随功能
  - [ ] Windows 系统检测
  - [ ] macOS 系统检测
  - [ ] 自动切换逻辑
- [ ] 实现主题导入/导出功能
  - [ ] 导出为 JSON 文件
  - [ ] 从 JSON 文件导入
  - [ ] 主题分享功能

**验收标准：**
- 可以切换不同预设主题
- 可以创建和编辑自定义主题
- 主题切换有平滑过渡动画
- 设置面板实时预览主题效果
- 主题配置正确持久化保存

### 阶段6：优化与完善

**目标：** 性能优化，bug 修复，功能完善

**任务清单：**
- [ ] 优化图片加载性能
- [ ] 优化数据库查询
- [ ] 完善设置面板（含主题设置）
- [ ] 添加键盘快捷键自定义
- [ ] 添加数据导入/导出功能
- [ ] 全面测试各功能模块
- [ ] 修复发现的 bug

**验收标准：**
- 各功能运行稳定
- 无明显性能问题
- 用户交互流畅
- 主题系统正常工作

---

## 七、关键技术实现要点

### 7.1 图片预加载策略

```python
from PyQt6.QtCore import QThread, pyqtSignal
from collections import deque

class PreloadManager:
    def __init__(self, max_cache=10):
        self.cache = OrderedDict()
        self.max_cache = max_cache
        self.preload_queue = deque()
        
    def get_image(self, image_path):
        """获取图片，优先从缓存读取"""
        if image_path in self.cache:
            # 移动到末尾（最近使用）
            self.cache.move_to_end(image_path)
            return self.cache[image_path]
        
        # 从磁盘加载
        image = self._load_image(image_path)
        self._add_to_cache(image_path, image)
        return image
    
    def preload_images(self, image_paths):
        """预加载图片到缓存"""
        for path in image_paths:
            if path not in self.cache and path not in self.preload_queue:
                self.preload_queue.append(path)
        self._process_preload()
    
    def _add_to_cache(self, path, image):
        """添加图片到缓存，超出限制时移除最旧的"""
        if len(self.cache) >= self.max_cache:
            self.cache.popitem(last=False)
        self.cache[path] = image
```

### 7.2 快速搜索实现

```python
class SearchService:
    def __init__(self, db):
        self.db = db
        self._init_fts()
    
    def _init_fts(self):
        """初始化全文搜索"""
        self.db.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS series_fts USING fts5(
                name, author, tags,
                content='series',
                content_rowid='id'
            )
        """)
        # 创建触发器保持 FTS 索引同步
        
    def search(self, keyword):
        """执行搜索"""
        cursor = self.db.execute("""
            SELECT s.* FROM series s
            JOIN series_fts fts ON s.id = fts.rowid
            WHERE series_fts MATCH ?
            ORDER BY rank
        """, (keyword,))
        return cursor.fetchall()
```

### 7.3 异步图片加载

```python
from PyQt6.QtCore import QRunnable, QThreadPool, pyqtSignal, QObject

class ImageLoadSignals(QObject):
    loaded = pyqtSignal(str, object)  # path, pixmap

class ImageLoadTask(QRunnable):
    def __init__(self, image_path):
        super().__init__()
        self.image_path = image_path
        self.signals = ImageLoadSignals()
    
    def run(self):
        pixmap = QPixmap(self.image_path)
        self.signals.loaded.emit(self.image_path, pixmap)

class AsyncImageLoader:
    def __init__(self):
        self.thread_pool = QThreadPool()
        self.thread_pool.setMaxThreadCount(4)
    
    def load_async(self, image_path, callback):
        task = ImageLoadTask(image_path)
        task.signals.loaded.connect(callback)
        self.thread_pool.start(task)
```

### 7.4 主题系统实现

#### 7.4.1 颜色工具类

```python
class ColorUtils:
    """颜色处理工具类"""
    
    @staticmethod
    def hex_to_rgb(hex_color: str) -> tuple:
        """十六进制颜色转 RGB"""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) for i in (0, 2, 4))
    
    @staticmethod
    def rgb_to_hex(rgb: tuple) -> str:
        """RGB 转十六进制颜色"""
        return '#{:02x}{:02x}{:02x}'.format(*rgb)
    
    @staticmethod
    def lighten(hex_color: str, amount: float = 0.2) -> str:
        """亮化颜色"""
        r, g, b = ColorUtils.hex_to_rgb(hex_color)
        r = min(255, int(r + (255 - r) * amount))
        g = min(255, int(g + (255 - g) * amount))
        b = min(255, int(b + (255 - b) * amount))
        return ColorUtils.rgb_to_hex((r, g, b))
    
    @staticmethod
    def darken(hex_color: str, amount: float = 0.2) -> str:
        """暗化颜色"""
        r, g, b = ColorUtils.hex_to_rgb(hex_color)
        r = max(0, int(r * (1 - amount)))
        g = max(0, int(g * (1 - amount)))
        b = max(0, int(b * (1 - amount)))
        return ColorUtils.rgb_to_hex((r, g, b))
    
    @staticmethod
    def get_contrast_color(hex_color: str) -> str:
        """获取对比色（黑或白）"""
        r, g, b = ColorUtils.hex_to_rgb(hex_color)
        # 计算亮度
        luminance = (0.299 * r + 0.587 * g + 0.114 * b) / 255
        return '#FFFFFF' if luminance < 0.5 else '#000000'
```

#### 7.4.2 主题实时预览

```python
class ThemePreviewWidget(QWidget):
    """主题预览组件"""
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.current_theme = None
        self._setup_ui()
    
    def _setup_ui(self):
        """设置预览界面"""
        layout = QVBoxLayout(self)
        
        # 标题栏预览
        self.title_bar = self._create_title_bar_preview()
        layout.addWidget(self.title_bar)
        
        # 按钮预览
        self.button_preview = self._create_button_preview()
        layout.addWidget(self.button_preview)
        
        # 列表预览
        self.list_preview = self._create_list_preview()
        layout.addWidget(self.list_preview)
        
        # 阅读器预览
        self.reader_preview = self._create_reader_preview()
        layout.addWidget(self.reader_preview)
    
    def update_preview(self, theme: dict):
        """更新预览"""
        self.current_theme = theme
        stylesheet = ThemeStyleSheetGenerator.generate_main_stylesheet(theme)
        self.setStyleSheet(stylesheet)
        self.update()
```

#### 7.4.3 系统主题检测

```python
import platform
import ctypes
from PyQt6.QtCore import QObject, pyqtSignal

class SystemThemeDetector(QObject):
    """系统主题检测器"""
    
    theme_changed = pyqtSignal(bool)  # True = dark, False = light
    
    def __init__(self):
        super().__init__()
        self._is_dark = False
        self._setup_detection()
    
    def _setup_detection(self):
        """设置主题检测"""
        if platform.system() == 'Windows':
            self._setup_windows_detection()
        elif platform.system() == 'Darwin':
            self._setup_macos_detection()
    
    def _setup_windows_detection(self):
        """Windows 主题检测"""
        try:
            # 读取注册表获取系统主题设置
            import winreg
            registry = winreg.ConnectRegistry(None, winreg.HKEY_CURRENT_USER)
            key = winreg.OpenKey(registry,
                r'Software\Microsoft\Windows\CurrentVersion\Themes\Personalize')
            value, _ = winreg.QueryValueEx(key, 'AppsUseLightTheme')
            self._is_dark = (value == 0)
            winreg.CloseKey(key)
        except Exception:
            pass
    
    def _setup_macos_detection(self):
        """macOS 主题检测"""
        try:
            import subprocess
            result = subprocess.run(
                ['defaults', 'read', '-g', 'AppleInterfaceStyle'],
                capture_output=True, text=True
            )
            self._is_dark = 'Dark' in result.stdout
        except Exception:
            pass
    
    def is_dark_mode(self) -> bool:
        """当前是否为深色模式"""
        return self._is_dark
```

---

## 八、开发建议

### 8.1 代码规范

1. **命名规范**
   - 类名：大驼峰 (MainWindow, ImageLoader)
   - 函数/变量：小写下划线 (load_image, image_path)
   - 常量：全大写下划线 (MAX_CACHE_SIZE)

2. **文档注释**
   - 所有公共类和方法必须添加 docstring
   - 复杂逻辑添加行内注释

3. **错误处理**
   - 所有文件操作添加 try-except
   - 用户操作失败给出友好提示
   - 记录错误日志

### 8.2 调试技巧

1. 使用 PyQt6 的 `QT_LOGGING_RULES` 环境变量调试 Qt 问题
2. 使用 Python 的 `logging` 模块记录运行日志
3. 使用 `QTimer.singleShot` 进行延迟调试

### 8.3 性能优化建议

1. **图片处理**
   - 大图显示时先缩放再加载
   - 使用 QPixmapCache 缓存缩略图
   - 异步生成缩略图

2. **数据库**
   - 为常用查询字段添加索引
   - 批量操作使用事务
   - 大数据量使用分页查询

---

## 九、下一步行动

确认本计划后，建议按以下步骤开始开发：

1. **准备开发环境**
   ```bash
   python -m venv venv
   venv\Scripts\activate
   pip install PyQt6 Pillow
   ```

2. **创建项目结构**
   - 按照目录结构创建文件夹
   - 初始化 Git 仓库

3. **从阶段1开始**
   - 先实现基础框架
   - 逐步添加功能模块

如果你对这个开发计划有任何疑问或需要调整的地方，请随时告诉我！
