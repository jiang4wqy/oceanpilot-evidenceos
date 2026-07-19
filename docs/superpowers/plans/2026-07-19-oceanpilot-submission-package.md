# OceanPilot Submission Package Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 生成可直接用于报名的 Part 1、Part 2、来源清单、GitHub 图文首页和严格两页 PDF，并公开发布经过事实边界审查的仓库。

**Architecture:** 文案以 `docs/submission/` 为单一事实源；README 复用同一组边界和图片；PDF 由确定性 ReportLab 脚本读取三张已审核 PNG 生成，并用 pypdf、Poppler 和逐页 PNG 复核。所有交付只描述当前可验证基础原型与明确标注的入围后方案，不修改 Python 产品代码。

**Tech Stack:** Markdown、PNG、Python 3.12、ReportLab、pypdf、pdfplumber、Poppler、GitHub CLI

## Global Constraints

- 工作目录固定为 `C:\Users\lenovo\Documents\飞书比赛`；不得写入默认 Codex cwd。
- 不修改 `src/`、`tests/`、`pyproject.toml`、API 行为或现有测试。
- 当前可声称：建案、证据存储、完整度判断、revision、SQLite 原子事务与审计边界；本地 `717 passed`；5 条 OpenAPI 路径。
- 当前不可声称：AI 诊断已实现、飞书/Oceanpayment 已接入、真实商户数据、真实业务收益、远程 CI、生产就绪。
- `POST /api/v1/cases/{case_id}/diagnose` 当前固定返回 `HTTP 501 FEATURE_DEFERRED`。
- Part 1 固定为 224 个字符；Part 2 正文为 544 个字符，保留四个段间空行时为 552 个字符；百分比必须写成“试点目标”。
- 图片中的绿色表示当前原型，蓝色虚线表示离线资产，灰色表示规划接入，琥珀色只表示人工确认；图 2 左侧 501 关系必须由正文说明为停止边界，不得解释为回写链路。
- PDF 固定两页、A4 横向、中文无缺字、100% 缩放可读；最终路径固定为 `artifacts/OceanPilot-开题报告补充材料.pdf`。
- 不创建 `LICENSE`，不使用“开源”表述；公开仓库不等于授予复用许可。

---

### Task 1: 冻结报名文案与来源

**Files:**
- Modify: `docs/submission/registration-copy.md`
- Create: `docs/submission/sources.md`

**Interfaces:**
- Consumes: 已批准提交规格与公开来源
- Produces: 表单可直接粘贴的 224/548 字文案，以及每条外部事实的直接链接

- [ ] **Step 1: 写入最终 Part 1**

使用以下正文，不增删字符：

```text
Swift 2025研究显示，跨境支付异常调查消息中，超过72%的数据字段仍为自由文本。Stripe已按地区、币种和金额动态选择支付方式，Primer也用事件时间线还原请求与响应；一位G2验证用户却指出，数据虽在，历史交易与到账关系仍需人工梳理。这提示单点推荐和时间线尚未解决跨角色证据交接。OceanPilot因此以“商户成功案件＋证据契约”统一上下文、时间线和来源：缺证先补问，达到证据门槛后才输出带引用的候选原因，再由规则和人工完成责任路由。
```

- [ ] **Step 2: 写入最终 Part 2**

使用以下五段正文：

```text
1.【方案概述】OceanPilot不是问答机器人，而是跨境商户成功的案件与证据中枢。它围绕同一份“商户成功案件”组织资料、判断与交接，连接接入前支付建议与上线后异常协作。

2.【架构与模块】完整方案由飞书交互、案件证据中枢、诊断路由、只读数据、看板知识五层组成。商户或OP描述问题后，系统自动建案、识别资料缺口并向正确角色补问；证据达标后才给出带来源的候选原因和下一动作，由Workflow完成人审、派单与跟踪。

3.【核心创新】区别于普通问答机器人和数据看板，本方案将“商户成功案件”与“证据契约”结合：候选判断绑定来源、时间和版本；资料不足先补问，高风险动作必须人工确认。AI理解模糊表达，规则守住状态和责任判断，使协作可解释、可追溯。

4.【预期价值】以企业现有流程为基线，试点目标为：证据引用率和高风险动作人审率100%，资料到齐时间缩短30%，首次责任域命中率达到80%，案件改派次数降低30%；并跟踪人工升级率与重复问题复用率。

5.【可行性与推广】当前EvidenceOS基础原型已验证建案、证据存储、完整度判断和审计边界，并通过717项测试；飞书Agent、诊断编排和真实数据适配将在入围后接入。后续替换数据适配器、校准规则并完成场景验收后，可扩展至支付推荐、退款、拒付和对账。
```

- [ ] **Step 3: 建立来源清单**

`sources.md` 至少列出：比赛页、Oceanpayment 官方资料、Swift 2025 PDF、McKinsey 2025 Global Payments Report、Worldpay GPR 2026、Stripe Dynamic Payment Methods、Primer Payment Timeline、G2 Stripe Payments Reviews。每项说明“支持什么”与“不能推导什么”；G2 明确标记为定性个案。

- [ ] **Step 4: 验证字符数与过期表述**

运行一个 PowerShell 检查，从 Markdown 的 `PART1_START/PART1_END` 与 `PART2_START/PART2_END` 标记间提取正文，将 CRLF 统一为 LF 并只移除块首尾换行。Part 2 必须保留五段之间的四个空行（共 8 个 LF 字符）。预期：Part 1=`224`；Part 2 含空行=`552`、移除全部换行=`544`。确认 `README.md` 与 `docs/submission/` 不再出现过期的“无可验证原型”或“两天原型”表述。

### Task 2: 收录三张流程图并完善 README

**Files:**
- Create: `docs/assets/submission/fig-01-evidence-loop.png`
- Create: `docs/assets/submission/fig-02-layered-architecture.png`
- Create: `docs/assets/submission/fig-03-case-walkthrough.png`
- Modify: `README.md`

**Interfaces:**
- Consumes: 三张已审核用户原图
- Produces: README 可匿名访问的创新闭环、架构边界和合成案例

- [ ] **Step 1: 原样复制三张 PNG**

映射固定为：

```text
C:\Users\lenovo\AppData\Local\Temp\codex-clipboard-f8e5428c-6092-4aaa-8c5c-3a7f6881f457.png -> docs/assets/submission/fig-01-evidence-loop.png
C:\Users\lenovo\AppData\Local\Temp\codex-clipboard-ed316174-00f1-4901-bf4f-6a2b03e13507.png -> docs/assets/submission/fig-02-layered-architecture.png
C:\Users\lenovo\AppData\Local\Temp\codex-clipboard-24159e4d-a92d-4b56-aafd-c1cd4085da63.png -> docs/assets/submission/fig-03-case-walkthrough.png
```

复制后 SHA256 必须分别为 `EED7EAE7F19C5932EC6D42B41E71322627FBD461EFD62D494EFD400A22F02745`、`9179DED7AC8253E54BC3D0A721E2FF2DAB3BCD96635C280F7D166C3C1FA840F0`、`0E8905D4A027E5194036309D9024C685623CE1C54F6E925C991F94652E27BF53`。

- [ ] **Step 2: 在 README 中加入视觉叙事**

在 `Current Foundation Scope` 后、`Architecture` 前加入三个小节：`证据先行闭环`（图 1）、`一个合成支付异常如何进入协作案件`（图 3）、`当前原型与完整方案`（图 2）。图 2 下必须逐字写：`事实边界：诊断请求进入 API 后固定返回 HTTP 501 FEATURE_DEFERRED；离线规则当前未接入主链。图中左侧深蓝折线仅标示停止边界，不表示 501 反向调用 FastAPI。`

- [ ] **Step 3: 验证图片和 Markdown**

检查三张目标 PNG 可解码、尺寸为 `1671x941`、`1672x941`、`1672x941`；README 三条相对路径存在；`git diff --check` 通过。

### Task 3: 建立两页报告的文字单一事实源

**Files:**
- Create: `docs/submission/opening-report-supplement.md`

**Interfaces:**
- Consumes: Task 1 文案、Task 2 图片和 `sources.md`
- Produces: PDF 生成脚本可直接读取或人工复核的两页内容稿

- [ ] **Step 1: 写 Page 1 内容**

顺序固定为：标题 `01｜为什么不是“再做一个 Agent”`；一句定位；Swift 的 `>72% free-format` 事实；Stripe 与 Primer 的成熟能力；G2 定性信号；三个创新点；图 1；来源编号。不得把 G2 个案写成行业比例。

- [ ] **Step 2: 写 Page 2 内容**

顺序固定为：标题 `02｜证据内核已验证，完整飞书闭环按阶段接入`；图 2；已实现/离线资产/规划接入三状态；`717 passed` 与 `5 API paths`；四项试点目标；四阶段落地路线；合成数据与 501 边界。

- [ ] **Step 3: 交叉核对**

确认 Part 1、Part 2、README 和补充材料对“已实现/离线资产/规划接入”的分类一致；所有百分比均为外部来源事实或明确试点目标。

### Task 4: 生成并逐页验证 PDF

**Files:**
- Create: `scripts/build_submission_pdf.py`
- Create: `artifacts/OceanPilot-开题报告补充材料.pdf`
- Create temporarily: `tmp/pdfs/oceanpilot-submission-page-1.png`
- Create temporarily: `tmp/pdfs/oceanpilot-submission-page-2.png`

**Interfaces:**
- Consumes: `opening-report-supplement.md`、`sources.md`、Hero、图 1、图 2
- Produces: 恰好两页的 A4 横向 PDF

- [ ] **Step 1: 实现确定性 PDF 构建脚本**

脚本提供 `main() -> int`，用 ReportLab `landscape(A4)`、Windows Microsoft YaHei 字体、深海军蓝/海洋蓝/青绿色/琥珀色配色；使用 `ImageReader` 按比例缩放 PNG。页边距保持 10-12 mm，标题 24-28 pt，正文 10.5-12 pt，图注 9-10 pt，来源不低于 7.5 pt；两张主图显示宽度均不得低于 220 mm。第一页以图 1 为主，第二页以图 2 为主；图 3 只留在 README，避免 PDF 缩小后过密。所有正文、状态和来源均在脚本常量中明确给出，脚本不得联网。

- [ ] **Step 2: 生成 PDF 并做结构检查**

运行：

```powershell
& 'C:\Users\lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts\build_submission_pdf.py
& 'C:\Users\lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -c "from pypdf import PdfReader; r=PdfReader(r'artifacts/OceanPilot-开题报告补充材料.pdf'); s=[(float(p.mediabox.width),float(p.mediabox.height)) for p in r.pages]; assert len(r.pages)==2 and all(w>h and abs(w-841.89)<2 and abs(h-595.28)<2 for w,h in s); print(len(r.pages),s)"
```

预期：脚本 exit 0；页数打印 `2`；pypdf 报告 A4 横向页面尺寸。当前工作区未提供 Poppler，但 bundled Python 已验证包含 ReportLab `4.4.9`、pypdf `6.10.0`、pdfplumber `0.11.9` 与 PyMuPDF `1.28.0`。

- [ ] **Step 3: 渲染与视觉复核**

优先使用 Poppler；当前机器未发现 `pdftoppm`，因此本次使用 bundled PyMuPDF 按 150 DPI 等效分辨率渲染：

```powershell
& 'C:\Users\lenovo\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' -c "import fitz,pathlib; d=pathlib.Path(r'tmp/pdfs'); d.mkdir(parents=True,exist_ok=True); doc=fitz.open(r'artifacts/OceanPilot-开题报告补充材料.pdf'); [p.get_pixmap(matrix=fitz.Matrix(150/72,150/72),alpha=False).save(d/f'oceanpilot-submission-page-{i+1}.png') for i,p in enumerate(doc)]"
```

用 `view_image` 原始细节逐页检查：无裁切、重叠、乱码、黑方块；最小正文可读；图例、来源和当前/规划边界清晰。发现任何缺陷即修改脚本、重建、重渲染，直到两页零视觉缺陷。

### Task 5: 最终红队、提交与公开发布

**Files:**
- Verify all submission files
- Commit only the approved allowlist

**Interfaces:**
- Consumes: Tasks 1-4 的全部交付
- Produces: 公共 GitHub 仓库和可填入表单的匿名可访问链接

- [ ] **Step 1: 运行最终事实与安全扫描**

检查：Part 1=`224`、Part 2 含空行=`552`/无换行=`544`、PDF=2页、4张 PNG 可解码、`717 passed`、Ruff、compileall、5-path OpenAPI、`git diff --check`；扫描密钥、数据库、日志、临时目录、真实商户数据与越界表述。

- [ ] **Step 2: 独立审查全部差异**

审查员必须分别给出规格符合性与质量结论，并验证图 2 的 501 说明、PDF 两页可读性、来源可追溯、README/表单/PDF 边界一致。

- [ ] **Step 3: 提交 allowlist**

只提交：`README.md`、`docs/submission/**`、`docs/assets/submission/fig-*.png`、`scripts/build_submission_pdf.py`、`artifacts/OceanPilot-开题报告补充材料.pdf` 和本计划；不得提交 `tmp/`、`.superpowers/sdd/`、数据库或日志。

- [ ] **Step 4: 创建并推送公共仓库**

若 `origin` 仍为空，运行：

```powershell
gh repo create jiang4wqy/oceanpilot-evidenceos --public --source . --remote origin --push
```

若仓库已存在，则设置/验证 `origin` 后执行 `git push -u origin master`。不创建 release，不自动提交报名表。

- [ ] **Step 5: 匿名访问验证**

在未登录上下文验证仓库首页、README Hero、三张图、PDF 和 raw 链接均返回成功；只有全部通过后，才把 GitHub URL 交给用户填写报名表。
