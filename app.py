import streamlit as st
import pydicom
import pandas as pd
import io
import zipfile
import re
import warnings
import base64
from copy import deepcopy
from pathlib import Path

warnings.filterwarnings("ignore")

st.set_page_config(
    page_title="DICOM Header Editor | SwiftMR",
    page_icon="🏥",
    layout="wide"
)

# ──  ─────────────────────────────────────────────
def get_image_base64(path):
    try:
        with open(path, "rb") as f:
            return base64.b64encode(f.read()).decode()
    except:
        return None

logo_b64 = get_image_base64("logo.png")
logo_html = f'<img src="data:image/png;base64,{logo_b64}" style="width:44px;height:44px;object-fit:contain;">' if logo_b64 else "🏥"
sidebar_logo_html = f'<img src="data:image/png;base64,{logo_b64}" style="width:48px;height:48px;object-fit:contain;">' if logo_b64 else "🏥"

# ── Custom CSS ───────────────────────────────────────
st.markdown("""
<style>
.stApp { background-color: #0f1117; }

.airs-header {
    display: flex; align-items: center; gap: 16px;
    padding: 20px 28px;
    background: linear-gradient(135deg, #1a1f2e 0%, #0d1117 100%);
    border-bottom: 2px solid #00d4ff;
    margin-bottom: 32px;
    border-radius: 0 0 16px 16px;
}
.airs-logo-box {
    width: 52px; height: 52px;
    background: transparent;
    border-radius: 12px;
    display: flex; align-items: center; justify-content: center;
    flex-shrink: 0;
}
.airs-title h1 {
    margin: 0; font-size: 22px; font-weight: 800;
    background: linear-gradient(90deg, #00d4ff, #0066ff);
    -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    letter-spacing: 2px;
}
.airs-title p { margin: 2px 0 0; font-size: 13px; color: #8892a4; letter-spacing: 1px; }
.airs-badge {
    margin-left: auto;
    background: rgba(0,212,255,0.1);
    border: 1px solid rgba(0,212,255,0.3);
    color: #00d4ff; padding: 6px 14px;
    border-radius: 20px; font-size: 12px; font-weight: 600; letter-spacing: 1px;
}

.step-card {
    background: linear-gradient(135deg, #1a1f2e, #141820);
    border: 1px solid #2a3040; border-radius: 16px;
    padding: 20px 24px; margin-bottom: 16px;
    box-shadow: 0 4px 24px rgba(0,0,0,0.3);
}
.step-header { display: flex; align-items: center; gap: 12px; }
.step-number {
    width: 36px; height: 36px;
    background: linear-gradient(135deg, #00d4ff, #0066ff);
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-weight: 800; font-size: 16px; color: white;
    box-shadow: 0 2px 12px rgba(0,212,255,0.4); flex-shrink: 0;
}
.step-title { font-size: 18px; font-weight: 700; color: #e8eaf0; margin: 0; }

.success-banner {
    background: linear-gradient(135deg, rgba(0,200,100,0.15), rgba(0,150,80,0.1));
    border: 1px solid rgba(0,200,100,0.3);
    border-radius: 12px; padding: 14px 20px;
    color: #00c864; font-weight: 600;
    display: flex; align-items: center; gap: 10px; margin: 12px 0;
}

.sidebar-section-title {
    font-size: 12px; font-weight: 700; color: #00d4ff;
    letter-spacing: 1px; text-transform: uppercase;
    margin-bottom: 10px; padding-bottom: 6px;
    border-bottom: 1px solid #2a3040;
}
.how-step { display: flex; align-items: flex-start; gap: 10px; margin-bottom: 8px; }
.how-step-num {
    width: 20px; height: 20px; flex-shrink: 0;
    background: linear-gradient(135deg, #00d4ff, #0066ff);
    border-radius: 50%;
    display: flex; align-items: center; justify-content: center;
    font-size: 11px; font-weight: 700; color: white;
}
.how-step-text { font-size: 13px; color: #c8d0dc; line-height: 1.5; }
.mode-label {
    font-size: 11px; font-weight: 700; color: #8892a4;
    letter-spacing: 1px; text-transform: uppercase;
    margin: 12px 0 6px; display: flex; align-items: center; gap: 6px;
}
.mode-label::after { content: ''; flex: 1; height: 1px; background: #2a3040; }

.note-item {
    display: flex; align-items: flex-start; gap: 8px;
    margin-bottom: 8px; font-size: 13px; color: #c8d0dc;
}
.note-icon { font-size: 14px; flex-shrink: 0; }

.tag-row {
    display: flex; align-items: center; gap: 6px;
    padding: 5px 0; border-bottom: 1px solid #1e2535;
}
.tag-code {
    font-family: monospace; font-size: 11px; color: #00d4ff;
    background: rgba(0,212,255,0.08); padding: 2px 6px;
    border-radius: 4px; min-width: 100px; flex-shrink: 0;
}
.tag-name { font-size: 12px; color: #c8d0dc; flex: 1; }
.tag-vr {
    font-size: 11px; color: #8892a4; background: #1e2535;
    padding: 1px 5px; border-radius: 3px; font-family: monospace; flex-shrink: 0;
}
</style>
""", unsafe_allow_html=True)

# ── Header ───────────────────────────────────────────
st.markdown(f"""
<div class="airs-header">
    <div class="airs--box">{_html}</div>
    <div class="airs-title">
        <h1>SwiftMR</h1>
        <p>DICOM Header Editor &nbsp;·&nbsp; Internal Tool</p>
    </div>
    <div class="airs-badge">v2.0</div>
</div>
""", unsafe_allow_html=True)


# ── Utility Functions ────────────────────────────────
def parse_dicom(file_bytes):
    return pydicom.dcmread(io.BytesIO(file_bytes), force=True)

def extract_tags(ds):
    rows = []
    for elem in ds:
        try:
            tag_str = f"({elem.tag.group:04X},{elem.tag.element:04X})"
            value = str(elem.value) if not isinstance(elem.value, bytes) else f"[Binary {len(elem.value)} bytes]"
            rows.append({
                "Tag": tag_str,
                "Keyword": elem.keyword if not elem.tag.is_private else "Private Tag",
                "VR": str(elem.VR), "Value": value, "Private": elem.tag.is_private
            })
        except Exception:
            continue
    return rows

def apply_modifications_to_ds(ds, modifications):
    ds_copy = deepcopy(ds)
    results = []
    for tag_str, new_value in modifications.items():
        try:
            group, element = tag_str.strip("()").split(",")
            tag = pydicom.tag.Tag(int(group, 16), int(element, 16))
            if tag in ds_copy:
                vr = ds_copy[tag].VR
                old_value = str(ds_copy[tag].value)
                if vr in ["DS", "FL", "FD"]:
                    ds_copy[tag].value = float(new_value)
                elif vr in ["IS", "SL", "SS", "UL", "US"]:
                    ds_copy[tag].value = int(new_value)
                else:
                    ds_copy[tag].value = new_value
                results.append({"Tag": tag_str, "Keyword": ds_copy[tag].keyword,
                                 "Before": old_value, "After": new_value, "Status": "✅ Success"})
            else:
                results.append({"Tag": tag_str, "Keyword": "-",
                                 "Before": "-", "After": new_value, "Status": "⚠️ Not found"})
        except Exception as e:
            results.append({"Tag": tag_str, "Keyword": "-",
                             "Before": "-", "After": new_value, "Status": f"❌ Error: {e}"})
    output = io.BytesIO()
    ds_copy.save_as(output, write_like_original=True)
    return output.getvalue(), results

def process_zip(zip_bytes, modifications):
    input_zip  = zipfile.ZipFile(io.BytesIO(zip_bytes))
    output_buf = io.BytesIO()
    output_zip = zipfile.ZipFile(output_buf, "w", zipfile.ZIP_DEFLATED)
    all_results = []
    success_count = skip_count = error_count = 0
    file_list = [f for f in input_zip.namelist() if not f.endswith("/")]
    skip_exts = {".jpg",".jpeg",".png",".gif",".bmp",".txt",".xml",".json",".pdf",".zip"}

    for filename in file_list:
        file_bytes = input_zip.read(filename)
        ext = Path(filename).suffix.lower()
        if ext in skip_exts:
            output_zip.writestr(filename, file_bytes)
            skip_count += 1
            continue
        try:
            ds = pydicom.dcmread(io.BytesIO(file_bytes), force=True)
            if len(ds) < 3:
                output_zip.writestr(filename, file_bytes)
                skip_count += 1
                continue
            modified_bytes, results = apply_modifications_to_ds(ds, modifications)
            for r in results:
                r["File"] = filename
            all_results.extend(results)
            output_zip.writestr(filename, modified_bytes)
            success_count += 1
        except Exception as e:
            error_count += 1
            all_results.append({"File": filename, "Tag": "-", "Keyword": "-",
                                  "Before": "-", "After": "-", "Status": f"❌ Failed: {e}"})
            output_zip.writestr(filename, file_bytes)

    output_zip.close()
    return output_buf.getvalue(), all_results, {
        "total": len(file_list), "success": success_count,
        "skipped": skip_count, "errors": error_count
    }


# ── Session State ────────────────────────────────────
defaults = {
    "ds": None, "tags_df": None, "modifications": {},
    "filename": "", "modified_bytes": None, "mod_results": None,
    "upload_mode": None, "zip_bytes": None, "summary": None, "queue_msg": None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ════════════════════════════════════════════════════
# STEP 1 : Upload
# ════════════════════════════════════════════════════
st.markdown("""
<div class="step-card">
  <div class="step-header">
    <div class="step-number">1</div>
    <p class="step-title">Upload File</p>
  </div>
</div>""", unsafe_allow_html=True)

upload_mode = st.radio(
    "mode", ["🗂️ Single DICOM (.dcm)", "📦 Multiple DICOMs (.zip)"],
    horizontal=True, label_visibility="collapsed"
)

if "Single" in upload_mode:
    uploaded = st.file_uploader("Upload a DICOM file", type=["dcm","DCM"])
    if uploaded:
        if uploaded.name != st.session_state.filename:
            fb = uploaded.read()
            st.session_state.ds            = parse_dicom(fb)
            st.session_state.tags_df       = extract_tags(st.session_state.ds)
            st.session_state.filename      = uploaded.name
            st.session_state.upload_mode   = "single"
            st.session_state.zip_bytes     = None
            st.session_state.modifications = {}
            st.session_state.modified_bytes= None
            st.session_state.mod_results   = None
            st.session_state.summary       = None
            st.session_state.queue_msg     = None
        st.success(f"✅ Loaded: **{st.session_state.filename}** — {len(st.session_state.tags_df)} tags")
else:
    uploaded = st.file_uploader("Upload a ZIP file", type=["zip"])
    if uploaded:
        if uploaded.name != st.session_state.filename:
            zb = uploaded.read()
            with zipfile.ZipFile(io.BytesIO(zb)) as zf:
                file_list = [f for f in zf.namelist() if not f.endswith("/")]
            with st.expander(f"📂 {len(file_list)} files in ZIP", expanded=False):
                st.dataframe(pd.DataFrame({"File": file_list}), hide_index=True)
            first_dcm_bytes = first_dcm_name = None
            with zipfile.ZipFile(io.BytesIO(zb)) as zf:
                for fname in zf.namelist():
                    if fname.endswith("/"): continue
                    fb = zf.read(fname)
                    try:
                        ds_test = pydicom.dcmread(io.BytesIO(fb), force=True)
                        if len(ds_test) >= 3:
                            first_dcm_bytes = fb
                            first_dcm_name  = fname
                            break
                    except Exception:
                        continue
            if first_dcm_bytes:
                st.session_state.ds            = parse_dicom(first_dcm_bytes)
                st.session_state.tags_df       = extract_tags(st.session_state.ds)
                st.session_state.zip_bytes     = zb
                st.session_state.filename      = uploaded.name
                st.session_state.upload_mode   = "zip"
                st.session_state.modifications = {}
                st.session_state.modified_bytes= None
                st.session_state.mod_results   = None
                st.session_state.summary       = None
                st.session_state.queue_msg     = None
            else:
                st.error("❌ No valid DICOM files found in ZIP.")
        if st.session_state.filename:
            st.success(f"✅ ZIP loaded: **{st.session_state.filename}**")


# ════════════════════════════════════════════════════
# STEP 2 : Edit
# ════════════════════════════════════════════════════
if st.session_state.ds is not None:
    st.markdown("""
    <div class="step-card">
      <div class="step-header">
        <div class="step-number">2</div>
        <p class="step-title">View & Edit Tags</p>
      </div>
    </div>""", unsafe_allow_html=True)

    col1, col2 = st.columns([3, 1])
    with col1:
        search = st.text_input("🔍 Search Tags", placeholder="e.g. PatientName or 0010,0010")
    with col2:
        show_private = st.checkbox("Show Private Tags", value=True)

    df = pd.DataFrame(st.session_state.tags_df)
    if not show_private:
        df = df[df["Private"] == False]
    if search:
        esc = re.escape(search)
        mask = (
            df["Keyword"].str.contains(esc, case=False, na=False, regex=True) |
            df["Tag"].str.contains(esc, case=False, na=False, regex=True) |
            df["Value"].str.contains(esc, case=False, na=False, regex=True)
        )
        df = df[mask]

    st.caption(f"Showing **{len(df)}** tag(s)")

    col_a, col_b = st.columns([2, 3])
    with col_a:
        selected_tag = st.selectbox("Select tag to edit", df["Tag"].tolist(), key="tag_select")
    with col_b:
        if selected_tag:
            cur = df[df["Tag"] == selected_tag]["Value"].values[0]
            default_val = st.session_state.modifications.get(selected_tag, cur)
        else:
            default_val = ""
        new_value = st.text_input("New value", value=default_val)

    if st.button("📝 Queue Change", use_container_width=True, key="queue_btn"):
        val = new_value.strip()
        if not selected_tag:
            st.session_state.queue_msg = ("error", "Please select a tag.")
        elif not val:
            st.session_state.queue_msg = ("error", "Please enter a new value.")
        else:
            st.session_state.modifications[selected_tag] = val
            st.session_state.modified_bytes = None
            st.session_state.mod_results    = None
            st.session_state.summary        = None
            st.session_state.queue_msg      = ("success", f"Queued: **{selected_tag}** → `{val}`")

    if st.session_state.queue_msg:
        t, m = st.session_state.queue_msg
        st.success(m) if t == "success" else st.warning(m)

    if st.session_state.modifications:
        st.markdown("#### 📋 Pending Modifications")
        atdf = pd.DataFrame(st.session_state.tags_df)
        mod_data = []
        for tag, val in st.session_state.modifications.items():
            kw  = atdf[atdf["Tag"] == tag]["Keyword"].values
            ori = atdf[atdf["Tag"] == tag]["Value"].values
            mod_data.append({
                "Tag": tag,
                "Keyword": kw[0] if len(kw) else "Unknown",
                "Original": ori[0] if len(ori) else "-",
                "New Value": val
            })
        st.dataframe(pd.DataFrame(mod_data), use_container_width=True, hide_index=True)

        c1, c2 = st.columns([2, 3])
        with c1:
            if st.button("🗑️ Clear All", use_container_width=True):
                st.session_state.modifications  = {}
                st.session_state.modified_bytes = None
                st.session_state.mod_results    = None
                st.session_state.summary        = None
                st.session_state.queue_msg      = None
                st.rerun()
        with c2:
            tag_to_remove = st.selectbox("Remove specific tag",
                                          list(st.session_state.modifications.keys()),
                                          key="remove_select")
            if st.button("❌ Remove Selected", use_container_width=True):
                del st.session_state.modifications[tag_to_remove]
                st.session_state.modified_bytes = None
                st.session_state.mod_results    = None
                st.session_state.queue_msg      = None
                st.rerun()

    with st.expander("📄 View All Tags", expanded=False):
        def highlight_modified(row):
            if row["Tag"] in st.session_state.modifications:
                return ["background-color: rgba(0,212,255,0.1)"] * len(row)
            return [""] * len(row)
        st.dataframe(
            df.drop(columns=["Private"]).style.apply(highlight_modified, axis=1),
            use_container_width=True, height=400
        )

    # ════════════════════════════════════════════════
    # STEP 3 : Download
    # ════════════════════════════════════════════════
    st.markdown("""
    <div class="step-card">
      <div class="step-header">
        <div class="step-number">3</div>
        <p class="step-title">Apply & Download</p>
      </div>
    </div>""", unsafe_allow_html=True)

    if not st.session_state.modifications:
        st.info("💡 No modifications queued yet.")
    else:
        st.write(f"**{len(st.session_state.modifications)} tag(s)** queued.")

        if st.session_state.upload_mode == "single":
            if st.button("🚀 Apply Changes", type="primary", use_container_width=True):
                with st.spinner("Processing..."):
                    mb, results = apply_modifications_to_ds(
                        st.session_state.ds, st.session_state.modifications)
                st.session_state.modified_bytes = mb
                st.session_state.mod_results    = results

            if st.session_state.mod_results:
                st.dataframe(pd.DataFrame(st.session_state.mod_results),
                             use_container_width=True, hide_index=True)

            if st.session_state.modified_bytes:
                st.markdown('<div class="success-banner">✅ File ready for download!</div>',
                            unsafe_allow_html=True)
                st.download_button(
                    label="⬇️ Download Modified DICOM",
                    data=st.session_state.modified_bytes,
                    file_name=f"modified_{st.session_state.filename}",
                    mime="application/octet-stream",
                    use_container_width=True
                )

        elif st.session_state.upload_mode == "zip":
            st.info("📦 All DICOM files in ZIP will be modified.")

            if st.button("🚀 Apply to All & Create ZIP", type="primary", use_container_width=True):
                with st.spinner("Processing ZIP... Please wait."):
                    rb, all_results, summary = process_zip(
                        st.session_state.zip_bytes, st.session_state.modifications)
                st.session_state.modified_bytes = rb
                st.session_state.mod_results    = all_results
                st.session_state.summary        = summary

            if st.session_state.summary is not None:
                s = st.session_state.summary
                c1, c2, c3, c4 = st.columns(4)
                c1.metric("📁 Total",     s["total"])
                c2.metric("✅ Processed", s["success"])
                c3.metric("⏭️ Skipped",   s["skipped"])
                c4.metric("❌ Errors",     s["errors"])
                if s["success"] == 0:
                    st.error("❌ No DICOM files were processed!")

            if st.session_state.mod_results:
                with st.expander("📊 Modification Report", expanded=False):
                    st.dataframe(pd.DataFrame(st.session_state.mod_results),
                                 use_container_width=True, height=400, hide_index=True)

            if st.session_state.modified_bytes is not None:
                zip_name = st.session_state.filename.replace(".zip", "_modified.zip")
                st.markdown('<div class="success-banner">✅ ZIP ready for download!</div>',
                            unsafe_allow_html=True)
                st.download_button(
                    label="⬇️ Download Modified ZIP",
                    data=st.session_state.modified_bytes,
                    file_name=zip_name,
                    mime="application/zip",
                    use_container_width=True,
                    type="primary"
                )


# ── Sidebar ──────────────────────────────────────────
with st.sidebar:
    st.markdown(f"""
    <div style="text-align:center; padding:16px 0 20px;">
        <div style="width:56px;height:56px;margin:0 auto 10px;
            display:flex;align-items:center;justify-content:center;">
            {sidebar__html}
        </div>
        <div style="font-size:14px;font-weight:800;letter-spacing:2px;
            background:linear-gradient(90deg,#00d4ff,#0066ff);
            -webkit-background-clip:text;-webkit-text-fill-color:transparent;">
            SwiftMR</div>
        <div style="font-size:11px;color:#8892a4;margin-top:2px;letter-spacing:1px;">
            DICOM Header Editor</div>
    </div>
    """, unsafe_allow_html=True)

    st.divider()

    st.markdown('<div class="sidebar-section-title">📖 How to Use</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="mode-label">Single File</div>
    <div class="how-step"><div class="how-step-num">1</div><div class="how-step-text">Select <b>Single DICOM</b> mode</div></div>
    <div class="how-step"><div class="how-step-num">2</div><div class="how-step-text">Upload a <code>.dcm</code> file</div></div>
    <div class="how-step"><div class="how-step-num">3</div><div class="how-step-text">Select tag → Enter new value</div></div>
    <div class="how-step"><div class="how-step-num">4</div><div class="how-step-text">Queue Change → Apply → Download</div></div>
    <div class="mode-label" style="margin-top:14px;">Batch ZIP</div>
    <div class="how-step"><div class="how-step-num">1</div><div class="how-step-text">Select <b>Multiple DICOMs</b> mode</div></div>
    <div class="how-step"><div class="how-step-num">2</div><div class="how-step-text">Upload a <code>.zip</code> file</div></div>
    <div class="how-step"><div class="how-step-num">3</div><div class="how-step-text">Select tag → Enter new value</div></div>
    <div class="how-step"><div class="how-step-num">4</div><div class="how-step-text">Queue → Apply to All → Download ZIP</div></div>
    """, unsafe_allow_html=True)

    st.divider()

    st.markdown('<div class="sidebar-section-title">⚠️ Notes</div>', unsafe_allow_html=True)
    st.markdown("""
    <div class="note-item"><span class="note-icon">🔒</span><span>Original files are <b>never modified</b></span></div>
    <div class="note-item"><span class="note-icon">📦</span><span>Tags applied to <b>ALL</b> DICOM files in ZIP</span></div>
    <div class="note-item"><span class="note-icon">🚫</span><span>Do <b>not</b> upload real patient data (PHI)</span></div>
    """, unsafe_allow_html=True)

    st.divider()

    st.markdown('<div class="sidebar-section-title">🔧 Common Tags</div>', unsafe_allow_html=True)

    tab1, tab2, tab3 = st.tabs(["Standard", "AIRS Upload", "AIRS Recon"])

    with tab1:
        st.markdown("""
        <div class="tag-row"><span class="tag-code">(0020,000E)</span><span class="tag-name">SeriesInstanceUID</span></div>
        <div class="tag-row"><span class="tag-code">(0020,000D)</span><span class="tag-name">StudyInstanceUID</span></div>
        <div class="tag-row"><span class="tag-code">(0008,103E)</span><span class="tag-name">SeriesDescription</span></div>
        <div class="tag-row"><span class="tag-code">(0010,0010)</span><span class="tag-name">PatientName</span></div>
        <div class="tag-row"><span class="tag-code">(0008,0060)</span><span class="tag-name">Modality</span></div>
        <div class="tag-row"><span class="tag-code">(2001,9000)</span><span class="tag-name">Private (Philips)</span></div>
        """, unsafe_allow_html=True)

    with tab2:
        st.markdown("""
        <div class="tag-row"><span class="tag-code">(00E1,1010)</span><span class="tag-name">StudyId</span><span class="tag-vr">LO</span></div>
        <div class="tag-row"><span class="tag-code">(00E1,1011)</span><span class="tag-name">SeriesId</span><span class="tag-vr">LO</span></div>
        <div class="tag-row"><span class="tag-code">(00E1,1012)</span><span class="tag-name">ImageId</span><span class="tag-vr">LO</span></div>
        <div class="tag-row"><span class="tag-code">(00E1,1014)</span><span class="tag-name">UploadId</span><span class="tag-vr">LO</span></div>
        <div class="tag-row"><span class="tag-code">(00E1,1015)</span><span class="tag-name">DeviceId</span><span class="tag-vr">LO</span></div>
        <div class="tag-row"><span class="tag-code">(00E1,1030)</span><span class="tag-name">DispatchUnitId</span><span class="tag-vr">LO</span></div>
        <div class="tag-row"><span class="tag-code">(00E1,1031)</span><span class="tag-name">PostProcessingType</span><span class="tag-vr">LO</span></div>
        <div class="tag-row"><span class="tag-code">(00E1,1032)</span><span class="tag-name">SourceDispatchUnitId</span><span class="tag-vr">SH</span></div>
        <div class="tag-row"><span class="tag-code">(00E1,1033)</span><span class="tag-name">ADCType</span><span class="tag-vr">LO</span></div>
        <div class="tag-row"><span class="tag-code">(00E1,1034)</span><span class="tag-name">ADCNoiseThreshold</span><span class="tag-vr">LO</span></div>
        <div class="tag-row"><span class="tag-code">(00E1,1035)</span><span class="tag-name">BValue</span><span class="tag-vr">LO</span></div>
        <div class="tag-row"><span class="tag-code">(00E1,1036)</span><span class="tag-name">IsMarked</span><span class="tag-vr">CS</span></div>
        <div class="tag-row"><span class="tag-code">(00E1,1037)</span><span class="tag-name">NumberOfProjections</span><span class="tag-vr">IS</span></div>
        <div class="tag-row"><span class="tag-code">(00E1,1038)</span><span class="tag-name">RadialAngle</span><span class="tag-vr">IS</span></div>
        <div class="tag-row"><span class="tag-code">(00E1,1039)</span><span class="tag-name">Zoom</span><span class="tag-vr">LO</span></div>
        <div class="tag-row"><span class="tag-code">(00E1,1040)</span><span class="tag-name">SliceOrder</span><span class="tag-vr">LO</span></div>
        <div class="tag-row"><span class="tag-code">(00E1,1041)</span><span class="tag-name">Orientation</span><span class="tag-vr">LO</span></div>
        <div class="tag-row"><span class="tag-code">(00E1,1042)</span><span class="tag-name">Gap</span><span class="tag-vr">LO</span></div>
        <div class="tag-row"><span class="tag-code">(00E1,1043)</span><span class="tag-name">Thickness</span><span class="tag-vr">LO</span></div>
        <div class="tag-row"><span class="tag-code">(00E1,1044)</span><span class="tag-name">CalculatedBvalue</span><span class="tag-vr">SL</span></div>
        <div class="tag-row"><span class="tag-code">(00E1,1045)</span><span class="tag-name">PostprocessingMode</span><span class="tag-vr">LO</span></div>
        """, unsafe_allow_html=True)

    with tab3:
        st.markdown("""
        <div class="tag-row"><span class="tag-code">(00E1,1020)</span><span class="tag-name">InputSnr</span><span class="tag-vr">FL</span></div>
        <div class="tag-row"><span class="tag-code">(00E1,1021)</span><span class="tag-name">OutputSnr</span><span class="tag-vr">FL</span></div>
        <div class="tag-row"><span class="tag-code">(00E1,1022)</span><span class="tag-name">DenoisingLevel</span><span class="tag-vr">LO</span></div>
        <div class="tag-row"><span class="tag-code">(00E1,1023)</span><span class="tag-name">Sharpness</span><span class="tag-vr">FL</span></div>
        <div class="tag-row"><span class="tag-code">(00E1,1024)</span><span class="tag-name">ModelPath</span><span class="tag-vr">OB</span></div>
        <div class="tag-row"><span class="tag-code">(00E1,1025)</span><span class="tag-name">ModelHeader</span><span class="tag-vr">LO</span></div>
        <div class="tag-row"><span class="tag-code">(00E1,1026)</span><span class="tag-name">ModelVersion</span><span class="tag-vr">LO</span></div>
        <div class="tag-row"><span class="tag-code">(00E1,1034)</span><span class="tag-name">ADCNoiseThreshold</span><span class="tag-vr">LO</span></div>
        <div class="tag-row"><span class="tag-code">(00E1,1035)</span><span class="tag-name">BValue</span><span class="tag-vr">LO</span></div>
        """, unsafe_allow_html=True)

    st.divider()
    st.markdown("""
    <div style="text-align:center;font-size:11px;color:#4a5568;padding:8px 0;">
        © 2024 AIRS Medical Inc.<br>All rights reserved.
    </div>
    """, unsafe_allow_html=True)
