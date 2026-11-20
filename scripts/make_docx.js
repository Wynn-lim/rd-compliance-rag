// 生成《RAG 系统介绍》Word 文档到桌面
const {
  Document, Packer, Paragraph, TextRun, HeadingLevel, AlignmentType,
  Table, TableRow, TableCell, WidthType, BorderStyle, ShadingType,
  PageBreak, convertInchesToTwip,
} = require("docx");
const fs = require("fs");
const path = require("path");

const CN_HEAD = "Microsoft YaHei";
const CN_BODY = "SimSun";

const PAGE_W = 11906;          // A4
const MARGIN = 1440;
const CONTENT_W = PAGE_W - MARGIN * 2;   // 9026

const ACCENT = "1F4E79";
const GREY = "595959";
const LIGHT = "F2F6FA";

// ---------- 基础构件 ----------
function run(text, opts = {}) {
  return new TextRun({
    text,
    font: { ascii: opts.ascii || "Segoe UI", eastAsia: opts.cn || CN_BODY },
    size: opts.size || 21,               // 半点，21 = 10.5pt
    bold: !!opts.bold,
    italics: !!opts.italics,
    color: opts.color || "1A1A1A",
  });
}

function para(children, opts = {}) {
  return new Paragraph({
    children: Array.isArray(children) ? children : [children],
    spacing: { before: opts.before ?? 0, after: opts.after ?? 100, line: opts.line ?? 312 },
    alignment: opts.align,
    indent: opts.indent,
    border: opts.border,
    shading: opts.shading,
  });
}

function body(text, opts = {}) {
  return para(run(text, { size: 21, color: "262626", ...opts }), { after: 140, line: 320 });
}

function bullet(text, level = 0) {
  return new Paragraph({
    children: [run(text, { size: 21, color: "262626" })],
    bullet: { level },
    spacing: { after: 80, line: 312 },
  });
}

function h1(text) {
  return new Paragraph({
    text,
    heading: HeadingLevel.HEADING_1,
    spacing: { before: 360, after: 160 },
    border: { bottom: { style: BorderStyle.SINGLE, size: 8, color: "C9D6E2", space: 6 } },
  });
}

function h2(text) {
  return new Paragraph({
    text,
    heading: HeadingLevel.HEADING_2,
    spacing: { before: 260, after: 120 },
  });
}

// ---------- 表格 ----------
function cell(text, opts = {}) {
  const lines = Array.isArray(text) ? text : [text];
  return new TableCell({
    width: { size: opts.w, type: WidthType.DXA },
    shading: opts.fill ? { type: ShadingType.CLEAR, color: "auto", fill: opts.fill } : undefined,
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    children: lines.map((t, i) => new Paragraph({
      children: [run(t, {
        size: opts.size || 19,
        bold: opts.bold || i === 0 && opts.boldFirst,
        color: opts.color || "262626",
        cn: opts.cn || (opts.header ? CN_HEAD : CN_BODY),
      })],
      spacing: { before: 0, after: i === lines.length - 1 ? 0 : 60, line: 280 },
    })),
  });
}

function makeTable(rows, widths) {
  return new Table({
    columnWidths: widths,
    width: { size: CONTENT_W, type: WidthType.DXA },
    rows: rows.map((r, ri) => new TableRow({
      tableHeader: ri === 0,
      children: r.map((c, ci) => cell(c, {
        w: widths[ci],
        fill: ri === 0 ? ACCENT : (ri % 2 === 0 ? LIGHT : undefined),
        header: ri === 0,
        color: ri === 0 ? "FFFFFF" : "262626",
        bold: ri === 0,
      })),
    })),
  });
}

// ---------- 文档 ----------
const doc = new Document({
  styles: {
    default: {
      document: { run: { font: { ascii: "Segoe UI", eastAsia: CN_BODY }, size: 21 } },
      title: {
        run: { font: { ascii: "Segoe UI", eastAsia: CN_HEAD }, size: 40, bold: true, color: ACCENT },
        paragraph: { spacing: { before: 0, after: 120 }, alignment: AlignmentType.LEFT },
      },
      heading1: {
        run: { font: { ascii: "Segoe UI", eastAsia: CN_HEAD }, size: 28, bold: true, color: ACCENT },
        paragraph: { spacing: { before: 360, after: 160 }, keepNext: true },
      },
      heading2: {
        run: { font: { ascii: "Segoe UI", eastAsia: CN_HEAD }, size: 23, bold: true, color: "2E5F8A" },
        paragraph: { spacing: { before: 260, after: 120 }, keepNext: true },
      },
    },
  },
  sections: [{
    properties: {
      page: {
        size: { width: PAGE_W, height: 16838 },
        margin: { top: MARGIN, right: MARGIN, bottom: MARGIN, left: MARGIN },
      },
    },
    children: [
      // ===== 标题 =====
      new Paragraph({
        text: "研发合规与研发费用管理知识库",
        heading: HeadingLevel.TITLE,
        spacing: { after: 60 },
      }),
      new Paragraph({
        text: "RAG 问答系统介绍",
        heading: HeadingLevel.TITLE,
        spacing: { after: 200 },
      }),
      para([
        run("说明文档", { size: 19, color: GREY }),
        run("　|　", { size: 19, color: "BFBFBF" }),
        run("2026 年 11 月", { size: 19, color: GREY }),
        run("　|　", { size: 19, color: "BFBFBF" }),
        run("本地部署版", { size: 19, color: GREY }),
      ], { after: 260 }),

      // ===== 一 =====
      h1("一、它解决什么问题"),
      body("研发费用在中国有五个并行口径：会计核算、加计扣除、高企认定、IPO 发行监管、R&D 统计。"
        + "同一笔支出，五个口径下结论可能完全不同——比如委托研发，加计口径按 80% 计入委托方，"
        + "R&D 统计口径委托方不计入，方向是反的。"),
      body("市面上资料的通病是：只讲一个口径、只讲知识点不讲证据、只讲规则不讲判例。"
        + "而这个知识库的作者把这些拆成 70 个条目、逐条核过文号，还沉淀了 807 条勘误——"
        + "记录「市面常见说法其实是错的」。"),
      body("所以这个 RAG 的任务不是「找到相关内容」，而是在正确的口径下、带可溯源凭据地回答，"
        + "并且不被那些错误说法带跑。这是个比通用 RAG 难得多的题。"),

      // ===== 二 =====
      h1("二、核心设计：四层检索"),
      body("这是全项目最值钱的部分。知识库不是平铺的，是分层的，每层管一件事："),
      makeTable([
        ["层", "内容", "职责"],
        ["路由层", "条目索引（70 条的目录）", "先定位「该读哪个条目」"],
        ["知识层", "70 个 M 编号条目的正文", "答案主体"],
        ["纠错层", "807 条勘误 + 233 条铁律", "防污染（见下文）"],
        ["台账层", "政策文件总台账", "唯一能答「这条政策还有效吗」"],
      ], [1300, 3400, CONTENT_W - 4700]),
      para([run("")], { after: 120 }),
      h2("为什么纠错层必须单独拆开"),
      body("它记录的是「被否定的说法」。如果和正文混在一个池子里检索，模型会把「制造业加计提到 120%」"
        + "这种已被 4 处官方口径驳倒的传言，当成结论输出。施工规格原话是「必须单独分块、单独索引，"
        + "否则检索结果会互相污染」。"),
      body("实现上分两步：物理上单独分块、单独建索引；逻辑上它默认不跟正文抢名额，"
        + "而是作为附加提示返回。"),
      para([
        run("实测教训：", { bold: true, color: "A5450B" }),
        run("早期把纠错层并入主结果排名，10 题基线命中率从 10/10 掉到 9/10——因为它把 M07-01 挤出去了。"
          + "改成附加返回后两者兼得。", { color: "262626" }),
      ], {
        after: 160, line: 320,
        shading: { type: ShadingType.CLEAR, color: "auto", fill: "FDF6EF" },
        indent: { left: 120, right: 120 },
      }),

      // ===== 三 =====
      h1("三、一次查询怎么流动"),
      body("拿「研发支出资本化的五个条件是什么？」举例："),
      makeTable([
        ["步骤", "做什么"],
        ["1. 意图路由", "判断该查哪些层（本题：路由 + 知识 + 纠错常驻）"],
        ["2. 中文分词", "jieba 切词，但「财税〔2015〕119 号」「M06-15」「E-002」「120%」整体保护不拆开——文号差一位结论就错"],
        ["3. 双路召回", "BM25 关键词 top-60 ＋ bge 向量 top-60"],
        ["4. RRF 融合", "合并成 top-40"],
        ["5. 路由反推", "从路由层命中块里抽出 M 编号，给对应知识层块加权（本题反推出 M06-07，正是讲五条件那篇）"],
        ["6. 启发式重排", "文号精确命中 / M、E 编号命中 / L3-L4 状态 / 层权重 / 长度惩罚"],
        ["7. 交叉编码重排", "bge-reranker（本机 CPU 太慢，默认关）"],
        ["8. 拒答判定", "三道门（见下）"],
      ], [1900, CONTENT_W - 1900]),
      para([run("")], { after: 120 }),
      body("26 毫秒返回 6 条正文 + 5 条纠错提示。"),
      h2("为什么要双路混合"),
      body("因为纯向量在文号上是废物——「财税〔2015〕119 号」和「财税〔2015〕191 号」向量相似度极高，"
        + "但一个是基础文件一个是无关文件。BM25 的精确匹配补这个洞。"),

      // ===== 四 =====
      h1("四、拒答：三道门"),
      body("这个项目的硬规矩是「查不到就说查不到，绝不编造」。但单纯靠向量相似度分不开"
        + "「问的是库外事物」和「问的是库内事物」——实测问「澳大利亚 R&D Tax Incentive 的可返还比例」，"
        + "向量分能到 0.56，跟库内问题（0.63–0.73）只差一截，阈值卡得很危险。"),
      body("所以加了三道门："),
      bullet("向量余弦 ≥ 0.62（实测库内 0.63+，库外 ≤0.60）；"),
      bullet("或 BM25 ≥ 12（问句含文号 / M 编号时，即使语义分低也算强命中）；"),
      bullet("实体覆盖 ≥ 0.5：问句里的专有实体必须在检索结果里出现一部分。"),
      body("第 3 条最可靠。问「澳大利亚研发税收激励 R&D Tax Incentive」，它的专有实体在库内覆盖率是 0%，"
        + "直接判「库内暂无」。这是领域相关的信号，比任何语义分数都硬。"),

      // ===== 五 =====
      h1("五、现在到什么程度"),
      body("施工规格 8 步，前 6 步完成：分块（3823 块）、建索引、系统提示词、问答链路、前端、自测。"),
      makeTable([
        ["指标", "结果"],
        ["检索命中率", "10 / 10"],
        ["出处正确率", "9 / 10"],
        ["抗污染（纠错层召回）", "4 / 5"],
        ["拒答准确率", "3 / 3"],
      ], [4200, CONTENT_W - 4200]),
      para([run("")], { after: 120 }),
      body("唯一没过的是 BC-04 的 E-005 排第 6——bge-small-zh 在那个问句上的语义上限。"
        + "正确结论（五口径含 R&D 统计）仍在上下文里，系统不会照抄「四口径」错答。"
        + "没有为过单个用例去调参，那是对测试集过拟合。"),

      // ===== 六 =====
      h1("六、它和「直接问大模型」的差别在哪"),
      body("直接问豆包「研发支出资本化五个条件」，它会答得很流畅，但：可能漏口径、可能编条号、"
        + "可能把「专利到手即满足条件」这种倒置逻辑当结论——而库里专门有条目勘这个。"),
      body("这个系统答的每个字都带 M 编号和文号，点开能看原文，而且会主动弹出"
        + "「E-505：资本化的门槛是两条不是五项条件」「E-525：五条件被改写，第五条其实是 CAS 6 第四条」——"
        + "它知道你自己库里有哪些坑。这是 807 条勘误的价值，也是通用 RAG 给不了的。"),

      // ===== 附 =====
      new Paragraph({ children: [new PageBreak()] }),
      h1("附：当前状态一览"),
      makeTable([
        ["项目", "状态"],
        ["内容层（知识库 77 个 md）", "接手包原件，未改一字"],
        ["分块", "3823 块，按 ## 节切，四层元数据"],
        ["检索", "中文 BM25 + bge 向量 + RRF 融合 + 层路由 + 路由反推加权"],
        ["重排", "bge-reranker-v2-m3 已下载，CPU 太慢默认关闭"],
        ["生成", "可插拔：Anthropic / OpenAI 兼容 / 导出 prompt（当前模式）"],
        ["前端", "单页聊天 + 出处折叠 + 纠错层提示"],
        ["评测", "四指标，10 题基线 + 5 例 badcase + 3 条库外拒答"],
        ["单元测试", "12 / 12 通过"],
      ], [3000, CONTENT_W - 3000]),
      para([run("")], { after: 160 }),
      para([
        run("使用入口：", { bold: true }),
        run("http://127.0.0.1:8000", { color: ACCENT }),
        run("　（本地服务，Python 标准库实现，无框架依赖）", { color: GREY, size: 19 }),
      ], { after: 100 }),
      para([
        run("代码位置：", { bold: true }),
        run("E:\\code\\rd-rag", { color: ACCENT }),
        run("　（2307 行，README.md 含完整说明）", { color: GREY, size: 19 }),
      ], { after: 100 }),
    ],
  }],
});

const out = path.join("C:\\Users\\Administrator\\Desktop", "RAG系统介绍.docx");
Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(out, buf);
  console.log("written:", out, buf.length, "bytes");
});
