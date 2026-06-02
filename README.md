# 漫画阅读器

基于 PyQt6 的 Windows 桌面漫画管理与阅读工具，覆盖导入、整理、阅读、备份和导出这一整套本地使用流程。

## 当前状态

- 运行方式：源码运行或本地构建便携版
- 平台：Windows 10 / 11
- 依赖：Python 3.13、PyQt6、Pillow
- 数据存储：SQLite + 本地文件系统

## 主要功能

- 自动识别单集目录或多集父目录，支持拖放导入
- 导入时按图片哈希检测重复内容，支持跳过或报错
- 漫画按系列管理，支持作者、标签、收藏、已读/未读、自定义分组
- 阅读器支持滚轮/键盘翻页、缩放、全屏、书签、跳转和阅读进度恢复
- 支持将当前页设为封面，并自动维护封面缓存
- 支持完整数据备份、备份导入、单漫画导出和按分类导出
- 支持全局快捷键显示/隐藏主窗口

## 快速开始

开发环境运行：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
.\.venv\Scripts\python.exe run.py
```

构建便携版：

```powershell
.\packaging\build_portable.ps1
```

构建产物会输出到本地 `dist/` 和 `dist_portable/`，这两个目录属于可再生文件，不应提交到版本库。

## 项目结构

```text
man_hua_software/
├── app/                 # 应用源码
│   ├── main.py          # QApplication 入口
│   ├── config.py        # 路径和配置读写
│   ├── database.py      # SQLite 模式与连接
│   ├── services/        # 导入、书库、阅读、导出服务
│   ├── ui/              # 主窗口、导入弹窗、阅读器等 UI
│   └── utils/           # 封面、图片、全局快捷键等工具
├── data/                # 本地运行数据
├── docs/                # 补充文档
├── packaging/           # PyInstaller / NSIS / 构建脚本
├── plans/               # 历史规划文档
├── requirements.txt
└── run.py
```

## 数据目录

```text
data/
├── manga.db            # 主数据库
├── config.json         # 用户配置
├── covers/             # 封面源图与显示缓存
└── imports/            # copy 模式导入的原始图片
```

说明：

- 默认导入模式为 `copy`，图片会复制到 `data/imports/`
- `data/covers/` 只存封面相关缓存，不再额外复制整套漫画图片
- 删除系列时会同步清理对应导入目录和不再使用的封面缓存

## 开发说明

常用入口：

- `run.py`：本地启动脚本
- `app/main.py`：应用启动与服务装配
- `app/ui/main_window.py`：主界面和主要交互
- `app/ui/reader_window.py`：阅读器窗口
- `app/services/import_service.py`：导入与去重逻辑
- `app/services/library_service.py`：书库管理与封面维护
- `app/services/export_service.py`：备份与导出

补充文档：

- [打包说明](docs/packaging.md)
- [开发计划](plans/development_plan.md)

## 清理约定

以下目录是本地生成物，清理后可重新生成：

- `build/`
- `dist/`
- `dist_portable/`
- `__pycache__/`

以下目录保存真实运行数据，不应在整理时随意删除：

- `data/`
- `backups/`（如果后续产生备份文件）
