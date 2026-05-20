import streamlit as st
import pandas as pd
import re
from io import BytesIO

st.set_page_config(page_title="藥師諮詢紀錄輔助", layout="wide", page_icon="💊")

# ── 院內品項 CSV ──────────────────────────────────────────
@st.cache_data
def load_drug_db():
    try:
        df = pd.read_csv("drug_db.csv")
        name_col = next((c for c in df.columns if any(k in c.lower() for k in ['drug','name','藥品','品名'])), df.columns[0])
        atc_col  = next((c for c in df.columns if any(k in c.lower() for k in ['atc','class','分類'])), df.columns[1])
        return [{"name": str(r[name_col]).strip(), "atc": str(r[atc_col]).strip().upper()[:1]}
                for _, r in df.iterrows() if str(r[name_col]).strip()]
    except Exception:
        return []

drug_db = load_drug_db()

ATC_MAP = {
    "A":"A-消化/代謝","B":"B-血液","C":"C-心血管","D":"D-皮膚",
    "G":"G-泌尿生殖","H":"H-荷爾蒙","J":"J-抗感染","L":"L-腫瘤",
    "M":"M-肌肉骨骼","N":"N-神經","P":"P-寄生蟲","R":"R-呼吸",
    "S":"S-感覺","V":"V-其他","":"未分類"
}

FALLBACK_ATC = {
    "AMLODIPINE":"C","BESYLATE":"C","NIFEDIPINE":"C","METOPROLOL":"C",
    "ATENOLOL":"C","LOSARTAN":"C","VALSARTAN":"C","FUROSEMIDE":"C",
    "SPIRONOLACTONE":"C","ASPIRIN":"B","WARFARIN":"B","CLOPIDOGREL":"B",
    "METFORMIN":"A","FAMOTIDINE":"A","OMEPRAZOLE":"A","PANTOPRAZOLE":"A",
    "LINAGLIPTIN":"A","TRAJENTA":"A","GLIPIZIDE":"A","INSULIN":"A",
    "TENOFOVIR":"J","LAMIVUDINE":"J","AMOXICILLIN":"J","AZITHROMYCIN":"J",
    "ZOLPIDEM":"N","DIAZEPAM":"N","ALPRAZOLAM":"N","PREGABALIN":"N",
    "OXYBUTYNIN":"G","OXYBUTININ":"G","TAMSULOSIN":"G",
}

STATUS_LIST   = ["正常服用", "自備", "住院停用", "暫停"]
STATUS_COLORS = {"正常服用":"🟢","自備":"🟡","住院停用":"🔴","暫停":"🟣"}

EDU_OPTIONS = [
    "藥品外觀","劑型規格","劑量問題","給藥方式","藥物作用","投藥時間",
    "副作用","用藥安全性","藥物交互作用","藥物保存方式","中藥摻西藥",
    "特別用藥指導","藥物血中濃度監測","藥品動力學","藥品相容性",
    "藥品安定性","健保用藥規定","院內藥品品項問題",
]

SUGGEST_OPTIONS = [
    "劑量","頻率","療程(duration)","途徑","劑型","給藥(速率/濃度)",
    "相容性","適應症","禁忌","不適當併用","藥物選擇","交互作用",
    "血中/濃度監測","不良反應-提醒","不良反應-換藥","不良反應-停藥",
    "用藥政策","監測/檢驗項目","用藥衛教",
]

REF_OPTIONS = [
    "MICROMEDEX","Drug information","病歷查詢",
    "雲端藥歷","藥品仿單","本院處方集/維護系統","無參考文獻",
]

# ── 比對院內品項 ──────────────────────────────────────────
def lookup_atc(name: str) -> tuple:
    u = name.upper()
    words = [w for w in re.split(r"[^A-Z0-9]+", u) if len(w) > 2]
    best, best_score = None, 0
    for item in drug_db:
        db_u = item["name"].upper()
        score = sum(1 for w in words if w in db_u)
        if score > best_score:
            best, best_score = item, score
    if best and best_score > 0:
        return best["atc"], best["name"]
    for kw, atc in FALLBACK_ATC.items():
        if kw in u:
            return atc, ""
    return "", ""

# ── 藥品切割 ──────────────────────────────────────────────
def parse_drug_text(raw: str) -> list:
    drugs, stopped_set = [], set()
    m = re.search(r"住院[中]?[未]?(?:服用|使用)\s*([A-Za-z][\w\s\-/]*?)(?=\s{2,}|其餘|自備|$)", raw, re.I)
    if m:
        for n in m.group(1).strip().split():
            if len(n) > 2:
                stopped_set.add(n.upper())
    si = re.search(r"其餘自備|自備", raw)
    before = raw[:si.start()] if si else raw
    after  = raw[si.end():]   if si else ""
    extract = lambda s: [x.strip() for x in
        re.findall(r"[A-Z][A-Za-z0-9\-./]*(?:\s+(?:[A-Z][A-Za-z0-9\-./]*|[a-z]{1,5}\w*)){0,3}", s)
        if len(x.strip()) > 2]
    for n in stopped_set:
        atc, matched = lookup_atc(n)
        drugs.append({"name":n.title(),"status":"住院停用","atc":atc,"matched":matched,
                      "dose":"","freq":"","route":"","note":""})
    for n in extract(after):
        atc, matched = lookup_atc(n)
        drugs.append({"name":n,"status":"自備","atc":atc,"matched":matched,
                      "dose":"","freq":"","route":"","note":""})
    for n in extract(before):
        if not any(s in n.upper() for s in stopped_set):
            atc, matched = lookup_atc(n)
            drugs.append({"name":n,"status":"正常服用","atc":atc,"matched":matched,
                          "dose":"","freq":"","route":"","note":""})
    return drugs

# ── 輸出產生 ──────────────────────────────────────────────
def build_short(drugs, vitals, free_note):
    lines, by_status = [], {}
    for d in drugs:
        if not d["name"].strip(): continue
        entry = d["name"].strip()
        if d["atc"]: entry += f"[{d['atc']}]"
        det = "/".join(x for x in [d["dose"],d["freq"],d["route"]] if x)
        if det: entry += f"({det})"
        if d["note"]: entry += f"{{{d['note']}}}"
        by_status.setdefault(d["status"],[]).append(entry)
    for s, arr in by_status.items():
        lines.append(f"[藥品-{s}:{','.join(arr)}]")
    for v in vitals:
        parts = []
        if v["bp"]:    parts.append(f"BP:{v['bp']}")
        if v["gluAC"]: parts.append(f"GluAC:{v['gluAC']}")
        if v["gluPC"]: parts.append(f"GluPC:{v['gluPC']}")
        if v["hba1c"]: parts.append(f"HbA1c:{v['hba1c']}")
        if v["cr"]:    parts.append(f"Cr:{v['cr']}")
        if parts:
            date = f"({v['date']})" if v["date"] else ""
            lines.append(f"[追蹤{date}:{','.join(parts)}]")
    if free_note.strip():
        lines.append(f"[備註:{free_note.strip()}]")
    return "\n".join(lines)

def build_excel(tab, drugs, vitals, free_note, way, target, edu_or_suggest, ref, result):
    rows = [{"Tab":tab,"藥品名稱":d["name"],"用藥狀態":d["status"],
             "ATC":d["atc"],"ATC說明":ATC_MAP.get(d["atc"],""),
             "劑量":d["dose"],"頻次":d["freq"],"給藥途徑":d["route"],
             "藥品備註":d["note"],"院內對照品項":d.get("matched","")} for d in drugs]
    df_drug = pd.DataFrame(rows) if rows else pd.DataFrame(
        columns=["Tab","藥品名稱","用藥狀態","ATC","ATC說明","劑量","頻次","給藥途徑","藥品備註","院內對照品項"])
    df_meta = pd.DataFrame({
        "項目":["諮詢/建議方式","指導/建議對象","衛教/建議內容","參考資料","結果","備註"],
        "內容":[",".join(way),",".join(target),",".join(edu_or_suggest),
                ",".join(ref),result,free_note]})
    buf = BytesIO()
    with pd.ExcelWriter(buf, engine="openpyxl") as writer:
        df_drug.to_excel(writer, sheet_name="藥品清單", index=False)
        df_meta.to_excel(writer, sheet_name="諮詢資訊", index=False)
    return buf.getvalue()

# ── 藥品區塊 ──────────────────────────────────────────────
def drug_section(key_prefix):
    st.subheader("藥品清單")

    with st.expander("📋 貼上藥品文字 → 自動切割", expanded=True):
        paste = st.text_area("貼上原始文字", height=80, key=f"{key_prefix}_paste",
            placeholder="住院中未服用Oxybutinin  其餘自備  AMLODIPINE Besylate  Famotidine  Zolpidem")
        if st.button("⚡ 自動切割帶入", key=f"{key_prefix}_parse"):
            if paste.strip():
                st.session_state[f"{key_prefix}_drugs"] = parse_drug_text(paste)
                st.rerun()

    if f"{key_prefix}_drugs" not in st.session_state:
        st.session_state[f"{key_prefix}_drugs"] = []

    drugs = st.session_state[f"{key_prefix}_drugs"]

    if st.button("➕ 手動新增藥品", key=f"{key_prefix}_add"):
        drugs.append({"name":"","status":"正常服用","atc":"","matched":"",
                      "dose":"","freq":"","route":"","note":""})
        st.session_state[f"{key_prefix}_drugs"] = drugs
        st.rerun()

    to_del = None
    for i, d in enumerate(drugs):
        matched_hint = f"  ← {d['matched']}" if d.get("matched") else ""
        label = f"{STATUS_COLORS.get(d['status'],'⚪')} {d['name'] or '（未填）'}  {ATC_MAP.get(d['atc'],'')} {matched_hint}"

        # ── 每筆藥品：刪除按鈕在外面，不用展開就能刪 ──
        col_del, col_main = st.columns([0.06, 0.94])
        with col_del:
            # 用唯一 key：prefix + index + 版本號避免重複
            if st.button("✕", key=f"del_{key_prefix}_{i}", help="刪除"):
                to_del = i
        with col_main:
            with st.expander(label, expanded=(not d["name"])):
                c1, c2 = st.columns([3, 1])
                d["name"]   = c1.text_input("藥品名稱", d["name"], key=f"{key_prefix}_name_{i}")
                d["status"] = c2.selectbox("用藥狀態", STATUS_LIST,
                    STATUS_LIST.index(d["status"]) if d["status"] in STATUS_LIST else 0,
                    key=f"{key_prefix}_status_{i}")
                atc_keys   = list(ATC_MAP.keys())
                atc_labels = [f"{k} {v}" if k else "未分類" for k, v in ATC_MAP.items()]
                cur_idx    = atc_keys.index(d["atc"]) if d["atc"] in atc_keys else atc_keys.index("")
                sel_atc    = st.radio("ATC 分類", atc_labels, index=cur_idx,
                                      horizontal=True, key=f"{key_prefix}_atc_{i}")
                d["atc"] = atc_keys[atc_labels.index(sel_atc)]
                if d.get("matched"):
                    st.caption(f"院內對照：{d['matched']}")
                ca, cb, cc = st.columns(3)
                d["dose"]  = ca.text_input("劑量",     d["dose"],  placeholder="5mg",    key=f"{key_prefix}_dose_{i}")
                d["freq"]  = cb.text_input("頻次",     d["freq"],  placeholder="QD/BID", key=f"{key_prefix}_freq_{i}")
                d["route"] = cc.text_input("給藥途徑", d["route"], placeholder="PO/IV",  key=f"{key_prefix}_route_{i}")
                d["note"]  = st.text_input("個別備註", d["note"],  placeholder="特殊說明…", key=f"{key_prefix}_dnote_{i}")

    if to_del is not None:
        drugs.pop(to_del)
        st.session_state[f"{key_prefix}_drugs"] = drugs
        st.rerun()

    st.session_state[f"{key_prefix}_drugs"] = drugs
    return drugs

# ── 追蹤數值 ──────────────────────────────────────────────
def vital_section(key_prefix):
    st.subheader("追蹤數值")
    if f"{key_prefix}_vitals" not in st.session_state:
        st.session_state[f"{key_prefix}_vitals"] = []
    vitals = st.session_state[f"{key_prefix}_vitals"]
    if st.button("➕ 新增追蹤", key=f"{key_prefix}_vadd"):
        vitals.append({"date":"","bp":"","gluAC":"","gluPC":"","hba1c":"","cr":""})
        st.rerun()
    to_del = None
    for i, v in enumerate(vitals):
        cols = st.columns([1,1,1,1,1,1,0.3])
        v["date"]  = cols[0].text_input("日期",  v["date"],  placeholder="3/2", key=f"{key_prefix}_vd_{i}")
        v["bp"]    = cols[1].text_input("BP",    v["bp"],    placeholder="141", key=f"{key_prefix}_vb_{i}")
        v["gluAC"] = cols[2].text_input("GluAC", v["gluAC"], placeholder="140", key=f"{key_prefix}_vga_{i}")
        v["gluPC"] = cols[3].text_input("GluPC", v["gluPC"], placeholder="",    key=f"{key_prefix}_vgp_{i}")
        v["hba1c"] = cols[4].text_input("HbA1c", v["hba1c"], placeholder="",   key=f"{key_prefix}_vh_{i}")
        v["cr"]    = cols[5].text_input("Cr",    v["cr"],    placeholder="",    key=f"{key_prefix}_vc_{i}")
        if cols[6].button("✕", key=f"{key_prefix}_vdel_{i}"):
            to_del = i
    if to_del is not None:
        vitals.pop(to_del)
        st.rerun()
    st.session_state[f"{key_prefix}_vitals"] = vitals
    return vitals

# ════════════════════════════════════════════════════════
st.title("💊 藥師諮詢紀錄輔助工具")
db_count = len(drug_db)
if db_count:
    st.caption(f"✅ 院內品項已載入：{db_count} 筆")
else:
    st.caption("⚠️ 未找到 drug_db.csv，使用內建對照表。")

tab1, tab2 = st.tabs(["📋 諮詢紀錄", "💬 藥事建議"])

# ── Tab1 ─────────────────────────────────────────────────
with tab1:
    col_l, col_r = st.columns(2)
    with col_l:
        way    = st.multiselect("諮詢方式", ["電話諮詢","門診諮詢","查房當面諮詢"], key="way")
        target = st.multiselect("指導對象", ["本人","家屬","看護","醫師","護理師","藥師"], key="target")
        ref    = st.multiselect("參考資料", REF_OPTIONS, key="ref")
        result = st.radio("諮詢結果", ["完成","未完成"], horizontal=True, key="result")
    with col_r:
        edu = st.multiselect("衛教內容", EDU_OPTIONS, key="edu")

    drugs1  = drug_section("c")
    vitals1 = vital_section("c")

    st.subheader("自由備註")
    free1 = st.text_area("", max_chars=200, height=80, key="free1", placeholder="其他說明…（200字以內）")
    st.caption(f"{len(free1)}/200 字")

    st.divider()
    if st.button("⚡ 產生結構化文字", type="primary", key="gen1"):
        parts = []
        if way:    parts.append(f"[方式:{','.join(way)}]")
        if target: parts.append(f"[對象:{','.join(target)}]")
        if edu:    parts.append(f"[衛教:{','.join(edu)}]")
        if ref:    parts.append(f"[參考:{','.join(ref)}]")
        if result: parts.append(f"[結果:{result}]")
        short = "\n".join(parts) + ("\n" if parts else "") + build_short(drugs1, vitals1, free1)
        st.session_state["out1"] = short
        st.session_state["out1_len"] = len(short.replace("\n",""))

    if "out1" in st.session_state:
        n = st.session_state["out1_len"]
        color = "🔴" if n > 200 else "🟡" if n > 160 else "🟢"
        st.markdown(f"**HIS 備註欄輸出** {color} {n}/200 字")
        st.code(st.session_state["out1"], language=None)
        if n > 200:
            st.warning("⚠️ 超過 200 字！請刪減項目或縮短備註。")
        st.download_button("📥 下載完整 Excel", 
            build_excel("諮詢紀錄", drugs1, vitals1, free1, way, target, edu, ref, result),
            file_name="諮詢紀錄.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ── Tab2 ─────────────────────────────────────────────────
with tab2:
    col_l, col_r = st.columns(2)
    with col_l:
        sway    = st.multiselect("建議方式", ["電話","留訊息","當面建議"], key="sway")
        starget = st.multiselect("建議對象", ["主治醫師","住院醫師","專科護理師","護理師","病患"], key="starget")
        sresult = st.radio("建議結果", [], horizontal=True, key="sresult")
    with col_r:
        suggest = st.multiselect("建議內容", SUGGEST_OPTIONS, key="suggest")
        sref    = st.multiselect("參考資料", REF_OPTIONS, key="sref")

    drugs2  = drug_section("s")
    vitals2 = vital_section("s")

    st.subheader("自由備註")
    free2 = st.text_area("", max_chars=200, height=80, key="free2", placeholder="其他說明…（200字以內）")
    st.caption(f"{len(free2)}/200 字")

    st.divider()
    if st.button("⚡ 產生結構化文字", type="primary", key="gen2"):
        parts = []
        if sway:    parts.append(f"[建議方式:{','.join(sway)}]")
        if starget: parts.append(f"[建議對象:{','.join(starget)}]")
        if suggest: parts.append(f"[建議內容:{','.join(suggest)}]")
        if sref:    parts.append(f"[參考:{','.join(sref)}]")
        if sresult: parts.append(f"[建議結果:{sresult}]")
        short2 = "\n".join(parts) + ("\n" if parts else "") + build_short(drugs2, vitals2, free2)
        st.session_state["out2"] = short2
        st.session_state["out2_len"] = len(short2.replace("\n",""))

    if "out2" in st.session_state:
        n2 = st.session_state["out2_len"]
        color = "🔴" if n2 > 200 else "🟡" if n2 > 160 else "🟢"
        st.markdown(f"**HIS 備註欄輸出** {color} {n2}/200 字")
        st.code(st.session_state["out2"], language=None)
        if n2 > 200:
            st.warning("⚠️ 超過 200 字！")
        st.download_button("📥 下載完整 Excel",
            build_excel("藥事建議", drugs2, vitals2, free2, sway, starget, suggest, sref, sresult),
            file_name="藥事建議.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

# ── 分析工具 ─────────────────────────────────────────────
with st.expander("🔬 貼入 HIS 紀錄 → 解析結構"):
    raw = st.text_area("貼入原始紀錄", height=100, key="parse_raw",
        placeholder="[方式:電話諮詢]\n[藥品-自備:Warfarin[B]]\n[追蹤(3/2):BP:141,GluAC:140]")
    if st.button("🔍 解析", key="do_parse"):
        matches = re.findall(r'\[([^:]+):([^\]]+)\]', raw)
        if matches:
            df = pd.DataFrame(matches, columns=["欄位","內容"])
            st.dataframe(df, use_container_width=True)
            st.download_button("📥 下載 CSV",
                df.to_csv(index=False, encoding="utf-8-sig"), "parsed.csv", "text/csv")
        else:
            st.warning("未找到結構化欄位，請確認格式。")
