# PaperPDFRenamer · 论文 PDF 批量重命名

将下载后的杂乱 PDF 文件名，整理成便于查找的文献标题。

一个轻量的 Python 桌面工具：拖入文献 → 识别题录 → 核对预览 → 批量重命名。无需 Zotero，无需 API key。

## 功能

- **拖放添加**：支持多个 PDF 和文件夹，过滤重复文件；文件夹仅处理第一层。
- **自动识别**：从 PDF 首页和元数据提取 DOI，通过 Crossref 获取标题、年份和第一作者姓氏。无 DOI 时尝试内嵌标题。
- **三种格式**：仅标题、年份 - 标题、作者 - 年份 - 标题。
- **清晰预览**：文件编号、最多三行的文件名、选中后查看完整内容。
- **手动修正**：双击文件打开可调整大小的多行编辑窗口，支持 Ctrl + Enter 保存、Esc 取消；留空跳过。
- **避免覆盖**：遇到同名文件自动添加 `(2)`、`(3)` 等编号。
- **操作日志与撤销**：记录原名、新名和内容哈希，满足校验条件时可恢复原名。

命名示例（虚构题录）：

```text
download_12345.pdf
  → 2024 - Example study of thin films.pdf
  → Chen - 2024 - Example study of thin films.pdf
```

## 安装与启动

这是源码工具，不是免安装 EXE / APP。需要 **Python 3.10 或更新版本**，并包含 Tcl/Tk。推荐使用 [Python 官方安装包](https://www.python.org/downloads/)。首次安装需要联网。

先通过仓库的 **Code → Download ZIP** 下载并完整解压到固定位置，或使用 Git 克隆本仓库。

### Windows

1. 安装 Python，勾选 **Add Python to PATH**，保留 Tcl/Tk。
2. 双击 `Windows_Setup.bat`，安装虚拟环境及依赖。
3. 双击 `Windows_Start.bat` 启动。

也可以将 PDF 或文件夹拖到启动脚本上。需要桌面入口时，右键启动脚本创建快捷方式即可。正常启动程序即可，不必使用管理员权限。

### macOS

1. 安装带 Tcl/Tk 的官方 Python。
2. 在项目文件夹中运行：

```bash
chmod +x Mac_Setup.command Mac_Start.command
./Mac_Setup.command
./Mac_Start.command
```

后续可双击 `Mac_Start.command`。如遇 HTTPS 证书错误，运行官方 Python 附带的 `Install Certificates.command`。

### 手动安装

```bash
python -m venv .venv
```

Windows：

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe paper_renamer.py
```

macOS：

```bash
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python paper_renamer.py
```

## 使用方法

1. 将 PDF 或文件夹拖入窗口，也可以点击添加按钮。
2. 选择命名格式，点击 **识别 / 刷新预览**。
3. 核对标题。需要修正时双击该行，编辑新名称，无需填写 `.pdf`。
4. 点击 **执行重命名**，确认后在原目录修改文件名。
5. 如需恢复，点击顶部 **撤销一次操作**，选择对应日志。

修改命名格式后需重新识别。重新识别会覆盖当前手动填写的预览名称，建议先选择格式，再做手动修正。

## 数据与文件处理

- DOI 查询向 Crossref 发送 DOI，不上传 PDF 文件。首次安装从 PyPI 下载依赖。
- 只修改文件名，不修改 PDF 内容或元数据。
- 操作日志位于用户主目录下的 `PaperPDFRenamer_Logs`，包含本地文件路径；请勿将私人日志公开上传。
- 撤销要求原名未被占用、目标文件仍在记录位置且哈希一致；不满足条件的条目会跳过。
- 文件操作采用同目录硬链接后移除旧路径，因此需要支持硬链接的文件系统。部分网盘或可移动介质不支持，操作会报错。

## 已知限制

- 不提供 OCR；扫描版 PDF 可能需要手动填写名称。
- 只扫描首页和 PDF 元数据；多个 DOI、断行 DOI、特殊字符或 Crossref 缺少题录时可能识别失败。
- 找到 DOI 但联网查询失败时，不会自动回退到内嵌标题。
- 无 DOI 的 arXiv 文献仅尝试内嵌标题。
- 查询逐个执行，每次请求超时为 18 秒；大批量文献可能需要等待。
- 不同出版社的识别效果有差异，请在执行前核对预览。
- 非法文件名字符会替换为空格，过长名称会截短。
- 正在被阅读器占用的 PDF 可能无法重命名。处理期间请勿从其他程序移动或编辑文件。
- 已在 Windows 上使用并检查拖放、名称编辑和界面布局。包含 macOS 启动脚本，但尚未在真实 macOS 桌面验证。

## 项目结构

```text
paper_renamer.py        主程序、窗口和文件处理逻辑
setup.py               创建虚拟环境并安装依赖的辅助脚本
requirements.txt       固定版本依赖
Windows_Setup.bat       Windows 首次安装
Windows_Start.bat       Windows 启动
Mac_Setup.command      macOS 首次安装
Mac_Start.command      macOS 启动
使用说明.txt            离线使用说明
```

`setup.py` 是安装辅助脚本，不是用于构建 PyPI 包的 setuptools 配置。

## 问题反馈

请在 Issues 中说明系统版本、Python 版本、复现步骤和报错信息。分享截图或日志前，移除个人路径与敏感信息；请勿上传无权公开的论文 PDF。

## 第三方组件

- [pypdf](https://github.com/py-pdf/pypdf)：PDF 解析。
- [tkinterdnd2](https://github.com/Eliav2/tkinterdnd2)：系统文件拖放。
- [Crossref REST API](https://www.crossref.org/documentation/retrieve-metadata/rest-api/)：DOI 题录查询。
- Python 标准库 tkinter / ttk：桌面界面。

本仓库不包含第三方依赖的副本。第三方组件适用各自许可证。本项目暂未选择开源许可证；公开源码不等同于授予再分发或修改许可。
