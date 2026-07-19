# OceanPilot GitHub Hero Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将用户确认的 OceanPilot Hero 原图作为公开仓库首屏视觉，并让 README 在首屏内准确表达定位、创新点与当前能力边界。

**Architecture:** 原图保持像素不变，以稳定路径存放在 `docs/assets/submission/`。README 使用仓库相对路径引用图片，并在图片后提供可搜索、可复制的文本说明；所有“已实现”和“规划中”声明继续遵守已批准提交规格。

**Tech Stack:** PNG、GitHub Flavored Markdown、PowerShell、Git

## Global Constraints

- 不修改 Python 源码、API 行为或测试。
- 不加入官方 Logo、真实商户数据、真实交易数据或生产就绪声明。
- Hero 必须保留“参赛基础原型｜仅使用合成数据”边界。
- 不创建 `LICENSE`，不把公开仓库描述为“开源”。
- 图片目标路径固定为 `docs/assets/submission/oceanpilot-hero.png`。

---

### Task 1: 落盘经过审核的 Hero

**Files:**
- Create: `docs/assets/submission/oceanpilot-hero.png`

**Interfaces:**
- Consumes: `C:\Users\lenovo\AppData\Local\Temp\codex-clipboard-3858f45e-675c-4793-a927-1b6e0573654a.png`
- Produces: README 可稳定引用的 PNG 资产

- [x] **Step 1: 创建目标目录并复制原图**

运行：

```powershell
New-Item -ItemType Directory -Force -Path docs\assets\submission | Out-Null
Copy-Item -LiteralPath 'C:\Users\lenovo\AppData\Local\Temp\codex-clipboard-3858f45e-675c-4793-a927-1b6e0573654a.png' -Destination 'docs\assets\submission\oceanpilot-hero.png'
```

- [x] **Step 2: 验证文件签名、尺寸与内容哈希**

运行：

```powershell
Get-FileHash -Algorithm SHA256 docs\assets\submission\oceanpilot-hero.png
```

预期：源文件与目标文件 SHA256 完全一致；图片尺寸为 `1983 × 793`，PNG 可正常解码。

### Task 2: 重构 README 首屏

**Files:**
- Modify: `README.md`

**Interfaces:**
- Consumes: `docs/assets/submission/oceanpilot-hero.png`
- Produces: GitHub 首屏中的 Hero、项目一句话、三项创新与事实边界

- [x] **Step 1: 在标题下引用 Hero**

使用：

```markdown
![OceanPilot EvidenceOS：证据驱动的跨境商户成功协作系统](docs/assets/submission/oceanpilot-hero.png)
```

- [x] **Step 2: 将现有开场重写为简洁的评委视角摘要**

首屏必须依次包含：一句定位、三个创新点、当前原型边界；不得删除后续 API、运行说明与事实边界章节。

- [x] **Step 3: 检查图片替代文本与链接**

运行：

```powershell
rg -n "oceanpilot-hero|仅使用合成数据|HTTP 501|717 passed" README.md
```

预期：四类关键信息均能命中，且相对图片路径存在。

### Task 3: 交付验证

**Files:**
- Verify: `README.md`
- Verify: `docs/assets/submission/oceanpilot-hero.png`

**Interfaces:**
- Consumes: Task 1 和 Task 2 的输出
- Produces: 可提交、无无关改动的 Git 差异

- [x] **Step 1: 运行 Markdown 与差异检查**

运行：

```powershell
git diff --check
git status --short
git diff -- README.md
```

预期：`git diff --check` 无输出；仅出现计划、README 与 Hero 资产的预期改动。

- [x] **Step 2: 原图视觉复核**

检查：英文标题拼写、中文无错字、琥珀色只表示人工确认、左右安全边距完整、底部保留“仅使用合成数据”。

- [x] **Step 3: 提交当前最小里程碑**

```powershell
git add docs/superpowers/plans/2026-07-19-oceanpilot-github-hero.md README.md docs/assets/submission/oceanpilot-hero.png
git commit -m "docs: add OceanPilot submission hero"
```
