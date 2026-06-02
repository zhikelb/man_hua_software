# 打包说明

项目默认只维护便携版分发流程。

## 前提

- Windows 环境
- 已创建 `.\.venv`
- `requirements.txt` 中依赖可正常安装

## 构建命令

```powershell
.\packaging\build_portable.ps1
```

脚本会自动执行以下步骤：

1. 检查 `.\.venv\Scripts\python.exe`
2. 安装或更新项目依赖
3. 调用 PyInstaller 和 `packaging/build_exe.spec`
4. 重建 `dist/` 与 `dist_portable/`
5. 生成 `dist_portable/README.md`
6. 生成 `dist_portable/start_app.bat` 和 `dist_portable/启动应用.bat`

## 目录说明

- `packaging/build_portable.ps1`：唯一推荐的本地构建入口
- `packaging/build_exe.spec`：PyInstaller 配置
- `packaging/installer.nsi`：历史安装器占位脚本，只提示用户使用便携版

## 构建结果

- `dist/漫画阅读器_便携版/`：PyInstaller 原始输出
- `dist_portable/`：整理后的便携分发目录

`dist_portable/` 内应包含：

```text
dist_portable/
├── 漫画阅读器.exe
├── start_app.bat
├── 启动应用.bat
├── README.md
├── data/
└── _internal/
```

## 注意事项

- `build/`、`dist/`、`dist_portable/` 都是可再生目录，不提交版本库
- 构建脚本会删除旧的 `build/`、`dist/`、`dist_portable/`
- 如果需要保留用户数据，只备份 `data/`
