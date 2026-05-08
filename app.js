"use strict";

// ===== State =====
let allRecords = [];
let filtered = [];
let currentPage = 1;
let perPage = 50;

// 地域区分
const REGIONS = [
  { name: "北海道",    prefs: ["北海道"] },
  { name: "東北",      prefs: ["青森県","岩手県","宮城県","秋田県","山形県","福島県"] },
  { name: "関東",      prefs: ["茨城県","栃木県","群馬県","埼玉県","千葉県","東京都","神奈川県"] },
  { name: "中部",      prefs: ["新潟県","富山県","石川県","福井県","山梨県","長野県","岐阜県","静岡県","愛知県"] },
  { name: "近畿",      prefs: ["三重県","滋賀県","京都府","大阪府","兵庫県","奈良県","和歌山県"] },
  { name: "中国",      prefs: ["鳥取県","島根県","岡山県","広島県","山口県"] },
  { name: "四国",      prefs: ["徳島県","香川県","愛媛県","高知県"] },
  { name: "九州・沖縄", prefs: ["福岡県","佐賀県","長崎県","熊本県","大分県","宮崎県","鹿児島県","沖縄県"] },
];

const statusLabel = {
  digital:         { text: "デジタル公開",        cls: "badge-digital" },
  ndl_confirmed:   { text: "NDL所蔵（複写申請可）", cls: "badge-ndl" },
  library_catalog: { text: "所蔵図書館情報あり",   cls: "badge-catalog" },
  // 旧データとの互換
  ndl_catalog:     { text: "所蔵図書館情報あり",   cls: "badge-catalog" },
  unknown:         { text: "未確認",               cls: "badge-unknown" },
};

// ===== DOM refs =====
const searchEl    = document.getElementById("search");
const prefEl      = document.getElementById("pref-filter");
const statusCbs   = () => [...document.querySelectorAll(".status-cb")];
const yearFromEl  = document.getElementById("year-from");
const yearToEl    = document.getElementById("year-to");
const sortEl      = document.getElementById("sort-select");
const perPageEl   = document.getElementById("per-page");
const tbody       = document.getElementById("tbody");
const pagination  = document.getElementById("pagination");
const totalCount  = document.getElementById("total-count");
const resultCount = document.getElementById("result-count");
const resetBtn    = document.getElementById("reset-btn");
const overlay     = document.getElementById("modal-overlay");
const modalClose  = document.getElementById("modal-close");
const modalContent= document.getElementById("modal-content");

// ===== Load data =====
fetch("data.json")
  .then(r => r.json())
  .then(data => {
    allRecords = data;
    totalCount.textContent = data.length.toLocaleString();
    buildPrefFilter(data);
    applyFilters();
  })
  .catch(() => {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:40px;color:#c00">data.json の読み込みに失敗しました。</td></tr>';
  });

// ===== Build prefecture dropdown with regional groups =====
function buildPrefFilter(data) {
  const existingPrefs = new Set(data.map(r => r.pref).filter(Boolean));

  REGIONS.forEach(region => {
    const prefs = region.prefs.filter(p => existingPrefs.has(p));
    if (prefs.length === 0) return;

    const grp = document.createElement("optgroup");
    grp.label = region.name;
    prefs.forEach(p => {
      const opt = document.createElement("option");
      opt.value = p;
      opt.textContent = p;
      grp.appendChild(opt);
    });
    prefEl.appendChild(grp);
  });

  // 区分に含まれない都道府県（その他）
  const categorized = new Set(REGIONS.flatMap(r => r.prefs));
  const others = [...existingPrefs].filter(p => !categorized.has(p)).sort();
  if (others.length > 0) {
    const grp = document.createElement("optgroup");
    grp.label = "その他";
    others.forEach(p => {
      const opt = document.createElement("option");
      opt.value = p; opt.textContent = p;
      grp.appendChild(opt);
    });
    prefEl.appendChild(grp);
  }
}

// ===== Filter & sort =====
// checkbox の value セットは ndl_catalog も library_catalog に含める（互換）
function getStatusSet() {
  const checked = new Set(statusCbs().filter(cb => cb.checked).map(cb => cb.value));
  // ndl_catalog (旧データ) は library_catalog に含める
  if (checked.has("library_catalog")) checked.add("ndl_catalog");
  return checked;
}

function applyFilters() {
  const q       = searchEl.value.trim().toLowerCase();
  const pref    = prefEl.value;
  const statuses = getStatusSet();
  const yFrom   = parseInt(yearFromEl.value) || 0;
  const yTo     = parseInt(yearToEl.value)   || 9999;
  const sort    = sortEl.value;

  filtered = allRecords.filter(r => {
    if (!statuses.has(r.status)) return false;
    if (pref && r.pref !== pref) return false;
    if (q) {
      const hay = (r.title + r.subtitle + r.author + r.editor + r.org + r.publisher).toLowerCase();
      if (!hay.includes(q)) return false;
    }
    if (r.pub_date) {
      const y = parseInt(r.pub_date.slice(0, 4));
      if (y < yFrom || y > yTo) return false;
    }
    return true;
  });

  filtered.sort((a, b) => {
    switch (sort) {
      case "year-desc": return (b.pub_date || "").localeCompare(a.pub_date || "");
      case "year-asc":  return (a.pub_date || "").localeCompare(b.pub_date || "");
      case "pref-asc":  return (a.pref || "").localeCompare(b.pref || "", "ja");
      default:          return a.no - b.no;
    }
  });

  currentPage = 1;
  resultCount.textContent = `${filtered.length.toLocaleString()} 件`;
  render();
}

// ===== Render table =====
function render() {
  const start = (currentPage - 1) * perPage;
  const page  = filtered.slice(start, start + perPage);

  tbody.innerHTML = "";
  if (page.length === 0) {
    tbody.innerHTML = '<tr><td colspan="7" style="text-align:center;padding:30px;color:#999">該当する資料がありません</td></tr>';
    pagination.innerHTML = "";
    return;
  }

  const frag = document.createDocumentFragment();
  page.forEach(r => {
    const tr = document.createElement("tr");
    tr.dataset.no = r.no;

    const st = statusLabel[r.status] || statusLabel.unknown;
    const titleFull = [r.title, r.vol ? `第${r.vol}` : ""].filter(Boolean).join(" ");
    const yearStr   = r.pub_date ? r.pub_date.slice(0, 4) : "—";

    tr.innerHTML = `
      <td class="col-no">${r.no}</td>
      <td class="col-status"><span class="badge ${st.cls}">${st.text}</span></td>
      <td class="col-pref">${esc(r.pref)}</td>
      <td class="col-title title-cell">
        <div class="title-main" data-no="${r.no}">${esc(titleFull)}</div>
        ${r.subtitle ? `<div class="title-sub">${esc(r.subtitle)}</div>` : ""}
      </td>
      <td class="col-author">${esc(truncate(r.author || r.editor, 28))}</td>
      <td class="col-year">${yearStr}</td>
      <td class="col-links">
        <div class="links-cell">
          ${r.digital_url    ? `<a class="link-btn link-digital"  href="${r.digital_url}"    target="_blank" rel="noopener">NDL閲覧</a>` : ""}
          ${r.nabunken_url   ? `<a class="link-btn link-nabunken" href="${r.nabunken_url}"   target="_blank" rel="noopener">奈文研</a>` : ""}
          ${r.ndl_url        ? `<a class="link-btn link-ndl"      href="${r.ndl_url}"        target="_blank" rel="noopener">NDL検索</a>` : ""}
        </div>
      </td>
    `;
    frag.appendChild(tr);
  });
  tbody.appendChild(frag);

  tbody.querySelectorAll(".title-main").forEach(el => {
    el.addEventListener("click", () => {
      const rec = allRecords.find(r => r.no === +el.dataset.no);
      if (rec) openModal(rec);
    });
  });

  renderPagination();
}

// ===== Pagination =====
function renderPagination() {
  const total = Math.ceil(filtered.length / perPage);
  if (total <= 1) { pagination.innerHTML = ""; return; }

  const pages = buildPageList(currentPage, total);
  pagination.innerHTML = "";

  const prev = btn("‹ 前", currentPage === 1);
  prev.addEventListener("click", () => { currentPage--; render(); window.scrollTo(0,0); });
  pagination.appendChild(prev);

  pages.forEach(p => {
    if (p === "…") {
      const sp = document.createElement("span");
      sp.className = "page-ellipsis";
      sp.textContent = "…";
      pagination.appendChild(sp);
    } else {
      const b = btn(p, false);
      if (p === currentPage) b.classList.add("active");
      b.addEventListener("click", () => { currentPage = p; render(); window.scrollTo(0,0); });
      pagination.appendChild(b);
    }
  });

  const next = btn("次 ›", currentPage === total);
  next.addEventListener("click", () => { currentPage++; render(); window.scrollTo(0,0); });
  pagination.appendChild(next);
}

function buildPageList(cur, total) {
  if (total <= 7) return Array.from({length: total}, (_, i) => i + 1);
  const pages = [1];
  if (cur > 3) pages.push("…");
  for (let p = Math.max(2, cur - 1); p <= Math.min(total - 1, cur + 1); p++) pages.push(p);
  if (cur < total - 2) pages.push("…");
  pages.push(total);
  return pages;
}

function btn(label, disabled) {
  const b = document.createElement("button");
  b.className = "page-btn";
  b.textContent = label;
  b.disabled = disabled;
  return b;
}

// ===== Modal =====
function openModal(r) {
  const st = statusLabel[r.status] || statusLabel.unknown;

  const fields = [
    ["都道府県",   r.pref],
    ["管理機関",   r.org],
    ["副書名",     r.subtitle],
    ["巻次",       r.vol],
    ["シリーズ",   r.series + (r.series_no ? ` 第${r.series_no}` : "")],
    ["編著者",     r.author],
    ["編集機関",   r.editor],
    ["発行機関",   r.publisher],
    ["発行年月日", r.pub_date],
    ["NCID",       r.ncid],
    ["JP番号",     r.jp_no],
    ["総覧ID",     r.soram_id],
    ["備考",       r.note],
  ].filter(([, v]) => v);

  const dt = fields.map(([k, v]) => `<dt>${esc(k)}</dt><dd>${esc(v)}</dd>`).join("");

  const links = [
    r.digital_url  && `<a class="modal-link-btn modal-link-digital"  href="${r.digital_url}"  target="_blank" rel="noopener">NDL デジタルで読む</a>`,
    r.nabunken_url && `<a class="modal-link-btn modal-link-nabunken" href="${r.nabunken_url}" target="_blank" rel="noopener">奈文研サイトで見る</a>`,
    r.ndl_url      && `<a class="modal-link-btn modal-link-ndl"      href="${r.ndl_url}"      target="_blank" rel="noopener">NDL サーチで探す</a>`,
  ].filter(Boolean).join("");

  modalContent.innerHTML = `
    <div class="modal-title">${esc(r.title)}${r.vol ? `　${esc(r.vol)}` : ""}</div>
    ${r.subtitle ? `<div class="modal-subtitle">${esc(r.subtitle)}</div>` : ""}
    <span class="badge ${st.cls}" style="margin-bottom:14px;display:inline-block">${st.text}</span>
    <dl class="modal-grid">${dt}</dl>
    ${links ? `<div class="modal-links">${links}</div>` : ""}
  `;
  overlay.classList.remove("hidden");
}

modalClose.addEventListener("click", closeModal);
overlay.addEventListener("click", e => { if (e.target === overlay) closeModal(); });
document.addEventListener("keydown", e => { if (e.key === "Escape") closeModal(); });
function closeModal() { overlay.classList.add("hidden"); }

// ===== Helpers =====
function esc(s) {
  return (s || "").replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;");
}
function truncate(s, n) {
  if (!s) return "";
  return s.length > n ? s.slice(0, n) + "…" : s;
}

// ===== Event listeners =====
let debounceTimer;
function debounce(fn, ms) {
  clearTimeout(debounceTimer);
  debounceTimer = setTimeout(fn, ms);
}

searchEl.addEventListener("input",  () => debounce(applyFilters, 250));
prefEl.addEventListener("change",   applyFilters);
statusCbs().forEach(cb => cb.addEventListener("change", applyFilters));
yearFromEl.addEventListener("input",() => debounce(applyFilters, 400));
yearToEl.addEventListener("input",  () => debounce(applyFilters, 400));
sortEl.addEventListener("change",   applyFilters);
perPageEl.addEventListener("change",() => { perPage = +perPageEl.value; currentPage = 1; render(); });

resetBtn.addEventListener("click", () => {
  searchEl.value = "";
  prefEl.value   = "";
  yearFromEl.value = "";
  yearToEl.value   = "";
  statusCbs().forEach(cb => cb.checked = true);
  sortEl.value    = "no-asc";
  perPageEl.value = "50";
  perPage = 50;
  applyFilters();
});
