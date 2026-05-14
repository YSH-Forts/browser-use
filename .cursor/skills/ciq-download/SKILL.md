---
name: ciq-download
description: 从 CapitalIQ 下载投融资筛选数据的 Excel 文件。自动完成登录、导航到 Saved Screens、执行导出、点击 Download 按钮并保存文件。用于 CapitalIQ 数据导出、Saved Screen 下载、投融资数据分析，或用户提到 CIQ、CapitalIQ、S&P CapitalIQ、Saved Screen 等场景。
---

# CIQ 投融资数据下载

## 概述

本 Skill 自动完成 CapitalIQ 的完整下载流程：登录 → 导航到 Saved Screens → 打开筛选结果 → 点 Export Go → 新窗口下载 Excel。

### 工作流程图

```
[Chrome 启动] → [Okta SSO 登录 CapitalIQ]
    ↓
[点击 Screening 菜单] → [点击 Saved Screens 子菜单]
    ↓
[遍历 Saved Screens]
    ├─ 点击 Saved Screen 名称
    ├─ 等待筛选结果加载 (URL: /ScreenResults.aspx)
    ├─ 在 Export 区域选中 Excel，点 Go
    ├─ 新窗口自动打开 (Monitor.aspx)
    ├─ 等待报告生成 (Recently Completed Reports)
    └─ 点击 Download → 下载 Excel
    ↓
[将 .xls 文件从临时目录复制到目标目录]
```

## 使用方式

### 方式一：命令行（推荐）

```bash
python download_ciq.py "Saved Screen 名称" "D:\下载目录"
```

支持多个 Screen：
```bash
python download_ciq.py "主要经济体上市公司投资 23.1-8" "D:\CapitalIQ_Downloads"
python download_ciq.py "Screen A" "Screen B" "D:\数据"  # 多个 Screen
```

### 方式二：通过 Web UI

1. 在 Task 输入框中描述任务
2. 从右侧 Skills 面板选择 CIQ Skill 或直接粘贴命令行参数
3. 点击 Execute

## 完整任务描述模板

当用户触发本 Skill 时，自动填充以下任务描述：

```
从 CapitalIQ 下载投融资筛选数据：

1. 打开 Chrome，导航到 https://www.capitaliq.com/CIQDotNet/my/dashboard.aspx
2. 等待 5 秒让页面完全加载
3. 如果出现 Okta 登录页，输入用户名 meijun.sun@bowayalloy.com 和密码
4. 如果出现 Terms of Use 页面，点击接受
5. 等待登录完成，确认到达 dashboard

6. 点击顶部导航栏的 "Screening" 菜单
7. 在下拉菜单中点击 "Saved Screens"
8. 等待 5 秒让页面加载

9. 在 Saved Screens 列表中找到并点击对应的 Screen 名称
10. 等待 8 秒让筛选结果加载（URL 变为 ScreenResults.aspx）

11. 在筛选结果页面找到 Export 区域
12. 确保 Excel 选项被选中（点击 Excel 切换到 Excel 格式）
13. 点击 Excel 旁边的 "Go" 按钮（不是 excelReport 链接）
14. 等待 3 秒，新窗口会自动打开（Monitor.aspx）

15. 切换到新打开的窗口
16. 如果窗口未最大化，点击最大化按钮
17. 等待报告生成（Monitor.aspx 页面会显示 "Recently Completed Reports"）
18. 在 Recently Completed Reports 区域找到最新生成的报告
19. 点击该报告的 "Download" 按钮
20. 等待 10 秒让文件下载完成

21. 报告成功：确认下载完成，给出下载文件路径
```

## 技术实现要点

### 浏览器配置

```python
browser = Browser(
    headless=False,
    minimum_wait_page_load_time=2.0,
    accept_downloads=True,
    downloads_path=download_dir,
)
```

### URL 关键节点

| 阶段 | URL 模式 |
|------|---------|
| Dashboard | `/CIQDotNet/my/dashboard.aspx` |
| Saved Screens | `/CIQDotNet/Screening/SavedScreens.aspx` |
| 筛选结果 | `/CIQDotNet/Screening/ScreenResults.aspx` |
| Monitor（新窗口） | `/CIQDotNet/Monitor.aspx` |

### 关键交互点

1. **Screening 菜单**：顶部导航栏，需悬停或点击展开子菜单
2. **Saved Screens**：下拉子菜单项
3. **Export 区域**：筛选结果页面右侧，通常有 Excel 和 CSV 选项
4. **Go 按钮**：Excel 选项旁边的按钮，点击触发异步报告生成
5. **新窗口切换**：点击 Go 后必须切换到新打开的 Monitor 窗口
6. **Download 按钮**：Monitor 窗口中，Recently Completed Reports 区域内

### 异步报告生成处理

CapitalIQ 的 Excel 导出是**异步**的：

```
点击 Go → 打开 Monitor.aspx（状态: "Generating Report(s)") → 等待 → "Recently Completed Reports" 出现 → 点击 Download
```

**重要**：不要点击 `excelReport` 链接，那个会触发后台队列。必须点 Export 区域的 Go 按钮。

### 下载文件复制

报告下载到临时目录后，需要复制到用户指定目录：

```python
import shutil, glob
temp_pattern = os.path.join(os.environ['TEMP'], 'browser-use-downloads-*')
for temp_dir in glob.glob(temp_pattern):
    for fname in os.listdir(temp_dir):
        if fname.endswith(('.xls', '.xlsx')):
            src = os.path.join(temp_dir, fname)
            dst = os.path.join(download_dir, fname)
            shutil.copy2(src, dst)
            print(f'Downloaded: {dst}')
```

## 参数说明

| 参数 | 说明 | 示例 |
|------|------|------|
| `screen_name` | CapitalIQ 中 Saved Screen 的精确名称 | `主要经济体上市公司投资 23.1-8` |
| `download_dir` | 下载目标目录（必须最后一个参数） | `D:\CapitalIQ_Downloads` |

## 注意事项

- **前提条件**：Chrome 中已登录过 CapitalIQ（浏览器复用 profile）
- **Chrome 退出**：运行前确保 Chrome 完全退出，避免用户数据目录被锁
- **窗口切换**：Go 按钮点击后必须切换到新窗口，browser-use 的 switch tab action 可用
- **等待时间**：Monitor.aspx 页面报告生成通常需要 10-30 秒
- **文件名编码**：下载的 Excel 文件名是 URL 编码的汉字，如 `#20027;#35201;...;23.xls`

## 错误处理

- 如果在 Terms of Use 页面卡住：使用 JavaScript 强制点击 `#_chkIAgree` 和 `#btnAccept`
- 如果 Saved Screen 找不到：尝试模糊匹配，或使用 find_text 定位
- 如果 Monitor 窗口下载失败：检查文件是否已经在临时目录（某些情况下直接下载）
