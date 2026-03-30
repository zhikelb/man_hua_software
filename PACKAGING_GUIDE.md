# 漫画阅读器 - 打包部署完整指南

## 📦 打包完成！

当前版本推荐便携文件夹分发方案。

## 当前分发方案

| 方案 | 文件位置 | 特点 | 用途 |
|------|--------|------|------|
| **便携文件夹** | `dist_portable/` | 含运行所需组件，无需安装 | 默认分发 |

---

## 方案 1️⃣ - 便携文件夹版本（推荐）

### ✅ 优点
- ⚡ 完全便携，无需安装
- 📂 直接运行，包含所有文件
- 🔄 可任意移动位置
- 💾 自包含数据库和配置

### 📍 使用方法

```
dist_portable/
├── 漫画阅读器.exe          ← 主程序
├── start_app.bat           ← 启动器（推荐）
├── 启动应用.bat             ← 启动器（中文别名）
├── data/                   ← 应用数据（自动创建）
└── README.md               ← 使用说明
```

**启动步骤：**
1. 解压 `dist_portable` 文件夹到任意位置
2. 双击 `start_app.bat`（或 `启动应用.bat`）启动应用
3. 首次运行会自动创建数据目录

### ⚙️ 配置数据目录
- 数据库: `data/manga.db`
- 配置文件: `data/config.json`
- 封面图片: `data/covers/`
- 导入文件: `data/imports/`

---

## 便携构建命令（唯一推荐）

```powershell
# 一键构建便携版
./build_portable.ps1
```

输出目录：`dist/漫画阅读器_便携版/`
输出目录：`dist_portable/`

---

## 🚀 快速启动比较

### 便携版本
```
✅ 解压 → ✅ 双击 bat 文件 → 启动（无缝）
```

### 便携目录
```
✅ 构建 dist/漫画阅读器_便携版 → ✅ 复制整个文件夹 → ✅ 双击 exe 运行
```

---

## 📊 文件大小估计

| 方式 | 大小 | 备注 |
|------|------|------|
| 便携文件夹 | ~107MB | 无需安装，开箱即用 |
| 主程序 EXE | ~2.8MB | 仅引导程序，依赖同目录内部文件 |

---

## 🔧 常见问题

### Q: 应用无法启动怎么办？
**A:** 可能是数据文件夹权限问题
```powershell
# 方案：以管理员身份运行
右键 → "启动应用.bat" → "以管理员身份运行"
```

### Q: 能否修改数据保存位置？
**A:** 可以编辑 `data/config.json`
```json
{
  "data": {
    "path": "C:\\Users\\YourName\\AppData\\Local\\漫画阅读器"
  }
}
```

### Q: 如何备份用户数据？
**A:** 备份整个 `data` 文件夹
```powershell
Copy-Item -Path "data" -Destination "backup_data" -Recurse
```

### Q: 能否在多台电脑使用？
**A:** 可以，直接复制 `dist_portable` 文件夹到其他电脑

---

## 📥 分发建议

### 个人/小规模使用
👉 **推荐**: 使用 `dist_portable` 文件夹
- 最简单
- 无需安装
- 可随处携带

### 团队/企业使用
👉 **推荐**: 分发整个便携文件夹
- 可直接放在共享盘或 U 盘
- 更新时整包替换

---

## 🔄 更新和维护

### 更新版本步骤
1. 修改源代码
2. 重新运行打包命令：
   ```powershell
  .\build_portable.ps1
   ```
3. 分发新的 `dist_portable` 文件夹

### 清理临时文件
```powershell
Remove-Item -Path "build" -Recurse -Force
Remove-Item -Path "dist" -Recurse -Force
```

---

## 📝 打包命令速查

```powershell
# 1. 安装打包工具
.venv\Scripts\pip install pyinstaller

# 2. 一键生成便携文件夹
./build_portable.ps1
```

---

## ✨ 最终检查清单

- [x] 便携文件夹已创建（`dist/漫画阅读器_便携版/`）
- [x] 主程序已生成（`dist/漫画阅读器_便携版/漫画阅读器.exe`）
- [x] 运行数据将保存在程序目录下的 `data/`
- [x] 一键构建脚本已准备（`build_portable.ps1`）

---

**🎉 打包完成！选择一个方案进行分发吧！**
