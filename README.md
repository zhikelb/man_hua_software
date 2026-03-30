# 📚 漫画阅读器（Maven Hua）

> 一个功能完整的桌面漫画阅读管理系统 | A feature-rich desktop manga reader and management system

## ✨ 项目概述

这是一个基于 PyQt6 的现代化桌面应用，为漫画爱好者提供完整的**导入、管理、阅读**一体化解决方案。支持批量导入、智能去重、多维分类、历史记录等高级功能。

**当前版本**: MVP 1.0  
**开发状态**: ✅ 完成可分发版本  
**目标用户**: 漫画爱好者、个人及小型团队

---

## 🚀 快速开始

### 方案 A: 使用便携版本（推荐 ⭐）
```powershell
# 直接运行，无需安装
dist_portable\start_app.bat
```

### 方案 B: 直接运行 EXE
```powershell
dist\漫画阅读器_便携版\漫画阅读器.exe
```

### 方案 C: 开发环境运行
```powershell
# 1. 安装依赖
.venv\Scripts\python.exe -m pip install -r requirements.txt

# 2. 启动应用
.venv\Scripts\python.exe run.py
```

---

## ✨ 核心功能

### 📥 智能导入
- ✅ 单层文件夹导入（按文件名自然排序）
- ✅ 批量导入（按父目录子文件夹映射集数）
- ✅ copy 导入（复制到数据目录，离线可用）
- ✅ 智能去重（哈希比对，三种处理策略）

### 📚 完整管理
- ✅ 漫画信息录入（名称、作者、集数、标签）
- ✅ 漫画属性编辑（名称、作者、标签、所属分组）
- ✅ 自动合并同系列（更新总集数）
- ✅ 多维分类书架（全部、最喜欢、未读、已读、自定义分组）
- ✅ 分组管理（新建、重命名、删除）
- ✅ 灵活的标签系统

### 👁️ 专业阅读器
- ✅ 双击封面进入阅读模式
- ✅ 自动恢复上次阅读位置
- ✅ 流畅翻页（键盘、滚轮、阅读区左右按钮）
- ✅ 集末自动跳转下一集
- ✅ 多档位缩放与自适应窗口
- ✅ 高质量 / 性能模式切换
- ✅ 书签管理（添加、查看、跳转、删除）
- ✅ 图片右键菜单（添加为漫画封面、跳转到文件所在位置）

### 📤 导入导出与备份
- ✅ 备份所有数据（Zip）
- ✅ 导入备份数据（支持 zip 或目录，自动合并并输出错误报告）
- ✅ 导出当前漫画（支持多选漫画或按分组导出）
- ✅ 导出目录结构：漫画名 / 集名 / 图片内部名

### 💾 数据持久化
- ✅ SQLite 本地数据库
- ✅ JSON 配置文件
- ✅ 自动备份机制

---

## 📦 安装与运行

### 环境要求
| 项目 | 要求 |
|------|------|
| **操作系统** | Windows 10 / 11 (64-bit) |
| **Python** | 3.7+ （开发环境） |
| **依赖** | PyQt6, Pillow |

### 安装步骤

#### 方式 1: 便携版本（无需安装）✨ 推荐
```
1. 下载 dist_portable 文件夹
2. 双击 start_app.bat（或 启动应用.bat）
3. 完成！
```

#### 方式 2: 独立 EXE
```
1. 在 dist/漫画阅读器_便携版 目录找到 漫画阅读器.exe
2. 右键 → 创建快捷方式
3. 双击快捷方式运行
```

#### 方式 3: 从源代码运行
```powershell
# 激活虚拟环境
.venv\Scripts\Activate.ps1

# 安装依赖
pip install -r requirements.txt

# 启动应用
python run.py
```

### 方式 4: 构建便携包
```powershell
.\build_portable.ps1
```
输出目录：`dist_portable/`
同步构建目录：`dist/漫画阅读器_便携版/`

---

## 📂 项目结构

```
man_hua_software/
├── app/                          # 应用主包
│   ├── __init__.py
│   ├── main.py                  # 应用入口
│   ├── config.py                # 配置管理
│   ├── database.py              # 数据库模型
│   ├── services/                # 业务逻辑层
│   │   ├── import_service.py   # 导入服务
│   │   ├── library_service.py  # 书库服务
│   │   └── reader_service.py   # 阅读器服务
│   ├── ui/                      # UI层
│   │   ├── main_window.py      # 主窗口
│   │   ├── import_dialog.py    # 导入对话框
│   │   └── reader_window.py    # 阅读器窗口
│   └── utils/                   # 工具函数
│       ├── cover_generator.py  # 封面生成
│       └── image_files.py      # 文件处理
├── data/                        # 应用数据
│   ├── manga.db                # SQLite 数据库
│   ├── config.json             # 应用配置
│   ├── covers/                 # 动态生成/存储的封面
│   └── imports/                # 导入后的漫画图片
├── dist/                        # 编译输出（EXE）
├── dist_portable/              # 便携版本 ⭐
│   ├── 漫画阅读器.exe
│   ├── 启动应用.bat
│   ├── data/
│   └── README.md
├── build/                       # PyInstaller 构建文件
├── run.py                       # 启动脚本
├── requirements.txt            # Python 依赖
├── build_exe.spec             # PyInstaller 规范
├── installer.nsi              # NSIS 安装脚本
├── QUICK_START.md             # 快速开始指南
├── PACKAGING_GUIDE.md         # 打包部署指南
└── README.md                  # 此文件
```

---

## 🔧 开发技术栈

| 组件 | 技术 | 版本 |
|------|------|------|
| **框架** | PyQt6 | 6.6.0+ |
| **图像处理** | Pillow | 10.0.0+ |
| **数据库** | SQLite3 | 内置 |
| **打包工具** | PyInstaller | 6.19.0 |
| **Python** | Python | 3.13.0 |

---

## 📥 数据管理

### 数据目录结构
```
data/
├── manga.db          # SQLite 本地数据库
│   └── 漫画表、作者表、标签表、进度表等
├── config.json       # 应用配置文件
├── covers/           # 漫画封面图片缓存
└── imports/          # 全量导入的原始图片
```

### 数据库模式
```sql
-- 漫画表
CREATE TABLE mangas (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    author TEXT,
    total_volumes INTEGER,
    status TEXT,  -- "reading", "completed", "paused"
    tags TEXT,
    cover_path TEXT,
    rating REAL,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
)

-- 进度表
CREATE TABLE reading_progress (
    id INTEGER PRIMARY KEY,
    manga_id INTEGER,
    volume INTEGER,
    page INTEGER,
    last_read TIMESTAMP
)

-- 更多细节见 app/database.py
```

---

## ⚙️ 配置说明

### config.json 基本配置
```json
{
    "import": {
        "hash_check_on_duplicate": true,
        "duplicate_content_policy": "skip"  // skip/error/allow
    },
    "reader": {
        "preload_count": 2,
        "default_zoom": "fit",
        "key_bindings": {
            "toggle_window": ["Ctrl+Shift+S"],
            "global_toggle_window": ["Ctrl+Alt+M"],
            "reader_toggle_fullscreen": ["F"]
        }
    },
    "ui": {
        "icon_size": 140,
        "grid_cell_width": 180,
        "grid_cell_height": 290,
        "sort_by": "updated_at",
        "sort_order": "desc"
    }
}
```

---

## 📦 打包和分发

### 已生成的可分发版本

#### 1. 便携文件夹版本 ⭐ 推荐
```
用途: 直接分享和使用，无需安装
位置: dist_portable/
特点: 包含所有依赖，开箱即用
大小: ~150MB
```

#### 2. 独立 EXE 文件
```
用途: 快速分享
位置: dist/漫画阅读器.exe
特点: 单个文件
大小: ~90MB
```

#### 3. Windows 安装程序
```
用途: 专业企业级部署
脚本: installer.nsi
编译: makensis.exe installer.nsi
输出: dist/漫画阅读器_installer.exe (~150MB)
```

### 打包清单
- ✅ PyInstaller 配置（build_exe.spec）
- ✅ NSIS 安装脚本（installer.nsi）
- ✅ 一键便携构建脚本（build_portable.ps1）
- ✅ 便携版本（dist_portable/）
- ✅ 独立 EXE（dist/）
- ✅ 完整文档

详见 `PACKAGING_GUIDE.md`

---

## 🚀 使用指南

### 导入漫画

**方式 A: 单层导入**
```
选择图片文件夹
→ 设置漫画信息
→ 导入
```

**方式 B: 批量导入**
```
选择包含子文件夹的父目录
→ 按子文件夹自动映射集数
→ 启用智能去重
→ 批量导入
```

### 阅读漫画
```
1. 在书架中双击漫画封面
2. 进入阅读模式
3. 使用方向键翻页，自动记录进度
4. 下次打开自动定位上次位置
```

### 管理分类
```
自定义分组 → 拖拽漫画 → 自动保存
```

---

## 📋 当前限制（MVP）

- 🔲 高级统计面板（规划中）
- 🔲 批量导入向导（规划中）
- 🔲 自定义封面选择 UI（规划中）
- 🔲 网络同步功能（未规划）
- 🔲 Linux/Mac 支持（Windows only）

---

## 🔧 故障排除

### 应用无法启动
```
解决方案:
1. 确保 Windows 10+ 系统
2. 检查 UAC 权限
3. 尝试以管理员身份运行
4. 检查磁盘空间（最少 500MB）
```

### 图片无法显示  
```
解决方案:
1. 移除文件名中的特殊字符
2. 确保图片格式为 JPG/PNG
3. 检查图片文件完整性
```

### 数据丢失
```
预防措施:
1. 定期备份 data/ 文件夹
2. 不要删除 manga.db 文件
3. 使用版本控制管理配置
```

---

## 🔄 开发与维护

### 获取源代码
```powershell
git clone <repository>
cd man_hua_software
```

### 开发环境设置
```powershell
# 创建虚拟环境
python -m venv venv

# 激活虚拟环境
venv\Scripts\Activate.ps1

# 安装依赖
pip install -r requirements.txt

# 开发
python run.py
```

### 重新打包
```powershell
# 一键重建便携版（推荐）
.\build_portable.ps1
```

### 常用 git 流程
```powershell
# 查看改动
git status

# 提交代码
git add app README.md PACKAGING_GUIDE.md build_portable.ps1
git commit -m "feat: update portable build and documentation"
```

---

## 📊 项目统计

| 指标 | 数值 |
|------|------|
| **源代码文件** | 10+ |
| **总代码行数** | 2000+ |
| **支持的图片格式** | 10+ |
| **数据库表** | 5+ |
| **UI 组件** | 20+ |

---

## 📝 许可证

本项目仅供个人学习和使用。

---

## 📞 支持与反馈

- 📖 详细文档: 
  - [快速开始](QUICK_START.md)
  - [打包部署指南](PACKAGING_GUIDE.md)
  - [打包总结](PACKAGE_SUMMARY.md)

- 🐛 问题反馈: 检查 data/config.json 和应用日志

- 💡 功能建议: 欢迎提交需求

---

## 🎯 下一步计划（Post-MVP）

- [ ] 高级搜索和过滤
- [ ] 阅读统计面板
- [ ] 批量操作向导
- [ ] 自定义主题系统
- [ ] 性能优化（大量漫画场景）
- [ ] 云端同步（可选）

---

## 👤 开发者

**项目**: Man Hua Software (漫画软件)  
**版本**: MVP 1.0  
**发布日期**: 2026-03-29  
**状态**: ✅ 生产就绪

---

**感谢使用漫画阅读器！** 📚✨
