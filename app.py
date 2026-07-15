import streamlit as st
import pydicom
import pandas as pd
import io
import zipfile
import re
import warnings
from copy import deepcopy
from pathlib import Path

warnings.filterwarnings("ignore")

st.set_page_config(
    page_title="DICOM Header Editor",
    page_icon="🏥",
    layout="wide"
)

st.title("🏥 DICOM Header Editor")
st.caption("Upload a DICOM file or ZIP archive, modify header tags, and download the result.")

# ── Utility Functions ────────────────────────────────
def parse_dicom(file_bytes: bytes):
    return pydicom.dcmread(io.BytesIO(file_bytes), force=True)

def extract_tags(ds) -> list:
    rows = []
    for elem in ds:
        try:
            tag_str = f"({elem.tag.group:04X},{elem.tag.element:04X})"
            value = (
                str(elem.value)
                if not isinstance(elem.value, bytes)
                else f"[Binary {len(elem.value)} bytes]"
            )
            rows.append({
                "Tag":     tag_str,
                "Keyword": elem.keyword if not elem.tag.is_private else "Private Tag",
                "VR":      str(elem.VR),
                "Value":   value,
                "Private": elem.tag.is_private
            })
        except Exception:
            continue
    return rows

def apply_modifications_to_ds(ds, modifications: dict):
    ds_copy = deepcopy(ds)
    results = []
    for tag_str, new_value in modifications.items():
        try:
            group, element = tag_str.strip("()").split(",")
            tag = pydicom.tag.Tag(int(group, 16), int(element, 16))
            if tag in ds_copy:
                vr        = ds_copy[tag].VR
                old_value = str(ds_copy[tag].value)
                if vr in ["DS", "FL", "FD"]:
                    ds_copy[tag].value = float(new_value)
                elif vr in ["IS", "SL", "SS", "UL", "US"]:
                    ds_copy[tag].value = int(new_value)
                else:
                    ds_copy[tag].value = new_value
                results.append({
                    "Tag":     tag_str,
                    "Keyword": ds_copy[tag].keyword,
                    "Before":  old_value,
                    "After":   new_value,
                    "Status":  "Success"
                })
            else:
                results.append({
                    "Tag": tag_str, "Keyword": "-",
                    "Before": "-", "After": new_value,
                    "Status": "Tag not found"
                })
        except Exception as e:
            results.append({
                "Tag": tag_str, "Keyword": "-",
                "Before": "-", "After": new_value,
                "Status": f"Error: {e}"
            })
    output = io.BytesIO()
    ds_copy.save_as(output, write_like_original=True)
    return output.getvalue(), results

def process_zip(zip_bytes: bytes, modifications: dict):
    input_zip  = zipfile.ZipFile(io.BytesIO(zip_bytes))
    output_buf = io.BytesIO()
    output_zip = zipfile.ZipFile(output_buf, "w", zipfile.ZIP_DEFLATED)

    all_results   = []
    success_count = 0
    skip_count    = 0
    error_count   = 0

    file_list = [f for f in input_zip.namelist() if not f.endswith("/")]
    total     = len(file_list)
    skip_exts = {".jpg", ".jpeg", ".png", ".gif", ".bmp",
                 ".txt", ".xml", ".json", ".pdf", ".zip"}

    for idx, filename in enumerate(file_list):
        file_bytes = input_zip.read(filename)
        ext        = Path(filename).suffix.lower()

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
            all_results.append({
                "File": filename, "Tag": "-", "Keyword": "-",
                "Before": "-", "After": "-",
                "Status": f"Failed: {e}"
            })
            output_zip.writestr(filename, file_bytes)

    output_zip.close()

    return output_buf.getvalue(), all_results, {
        "total":   total,
        "success": success_count,
        "skipped": skip_count,
        "errors":  error_count
    }


# ── Session State Init ───────────────────────────────
defaults = {
    "ds":              None,
    "tags_df":         None,
    "modifications":   {},
    "filename":        "",
    "modified_bytes":  None,  # ← bytes 저장
    "mod_results":     None,
    "upload_mode":     None,
    "zip_bytes":       None,
    "summary":         None,
    "queue_msg":       None,
}
for k, v in defaults.items():
    if k not in st.session_state:
        st.session_state[k] = v


# ── STEP 1: File Upload ──────────────────────────────
st.header("① Upload File")

upload_mode = st.radio(
    "Select upload type",
    ["Single DICOM (.dcm)", "Multiple DICOMs (.zip)"],
    horizontal=True
)

if upload_mode == "Single DICOM (.dcm)":
    uploaded = st.file_uploader("Upload a DICOM file", type=["dcm", "DCM"])
    if uploaded:
        file_bytes = uploaded.read()
        st.session_state.ds             = parse_dicom(file_bytes)
        st.session_state.tags_df        = extract_tags(st.session_state.ds)
        st.session_state.filename       = uploaded.name
        st.session_state.upload_mode    = "single"
        st.session_state.zip_bytes      = None
        st.session_state.modifications  = {}
        st.session_state.modified_bytes = None
        st.session_state.mod_results    = None
        st.session_state.summary        = None
        st.session_state.queue_msg      = None
        st.success(f"Loaded: {uploaded.name} — {len(st.session_state.tags_df)} tags found")

else:
    uploaded = st.file_uploader("Upload a ZIP file containing DICOM files", type=["zip"])
    if uploaded:
        zip_bytes = uploaded.read()
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            file_list = [f for f in zf.namelist() if not f.endswith("/")]

        st.success(f"ZIP loaded: {uploaded.name} — {len(file_list)} files detected")

        with st.expander("View files in ZIP", expanded=False):
            st.dataframe(pd.DataFrame({"File": file_list}), hide_index=True)

        first_dcm_bytes = None
        first_dcm_name  = None
        with zipfile.ZipFile(io.BytesIO(zip_bytes)) as zf:
            for fname in zf.namelist():
                if fname.endswith("/"):
                    continue
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
            st.session_state.ds             = parse_dicom(first_dcm_bytes)
            st.session_state.tags_df        = extract_tags(st.session_state.ds)
            st.session_state.zip_bytes      = zip_bytes
            st.session_state.filename       = uploaded.name
            st.session_state.upload_mode    = "zip"
            st.session_state.modifications  = {}
            st.session_state.modified_bytes = None
            st.session_state.mod_results    = None
            st.session_state.summary        = None
            st.session_state.queue_msg      = None
            st.info(f"Tag list loaded from: {first_dcm_name}")
        else:
            st.error("No valid DICOM files found in the ZIP.")


# ── STEP 2: Tag Viewer & Editor ──────────────────────
if st.session_state.ds is not None:
    st.header("② View & Edit Tags")

    col1, col2 = st.columns([3, 1])
    with col1:
        search = st.text_input("Search Tags", placeholder="e.g. PatientName or 0010,0010")
    with col2:
        show_private = st.checkbox("Show Private Tags", value=True)

    df = pd.DataFrame(st.session_state.tags_df)
    if not show_private:
        df = df[df["Private"] == False]
    if search:
        escaped = re.escape(search)
        mask = (
            df["Keyword"].str.contains(escaped, case=False, na=False, regex=True) |
            df["Tag"].str.contains(escaped, case=False, na=False, regex=True) |
            df["Value"].str.contains(escaped, case=False, na=False, regex=True)
        )
        df = df[mask]

    st.caption(f"Showing {len(df)} tag(s)")
    st.subheader("Edit a Tag")

    col_a, col_b = st.columns([2, 3])
    with col_a:
        selected_tag = st.selectbox(
            "Select tag to edit",
            df["Tag"].tolist(),
            key="selected_tag_selectbox"
        )
    with col_b:
        if selected_tag:
            current_val = df[df["Tag"] == selected_tag]["Value"].values[0]
            default_val = st.session_state.modifications.get(selected_tag, current_val)
        else:
            default_val = ""
        new_value = st.text_input("New value", value=default_val)

    if st.button("📝 Queue Change", use_container_width=True, key="queue_btn"):
        val = new_value.strip() if new_value else ""
        if not selected_tag:
            st.session_state.queue_msg = ("error", "Please select a tag.")
        elif not val:
            st.session_state.queue_msg = ("error", "Please enter a new value.")
        else:
            st.session_state.modifications[selected_tag] = val
            st.session_state.modified_bytes = None
            st.session_state.mod_results    = None
            st.session_state.summary        = None
            st.session_state.queue_msg      = ("success", f"Queued: {selected_tag} → {val}")

    if st.session_state.queue_msg:
        msg_type, msg_text = st.session_state.queue_msg
        if msg_type == "success":
            st.success(msg_text)
        else:
            st.warning(msg_text)

    if st.session_state.modifications:
        st.subheader("📋 Pending Modifications")
        all_tags_df = pd.DataFrame(st.session_state.tags_df)
        mod_data = []
        for tag, val in st.session_state.modifications.items():
            kw  = all_tags_df[all_tags_df["Tag"] == tag]["Keyword"].values
            ori = all_tags_df[all_tags_df["Tag"] == tag]["Value"].values
            mod_data.append({
                "Tag":       tag,
                "Keyword":   kw[0] if len(kw) > 0 else "Unknown",
                "Original":  ori[0] if len(ori) > 0 else "-",
                "New Value": val
            })
        st.dataframe(pd.DataFrame(mod_data), use_container_width=True, hide_index=True)

        col_del, col_tag_del = st.columns([2, 3])
        with col_del:
            if st.button("Clear All", use_container_width=True):
                st.session_state.modifications  = {}
                st.session_state.modified_bytes = None
                st.session_state.mod_results    = None
                st.session_state.summary        = None
                st.session_state.queue_msg      = None
                st.rerun()
        with col_tag_del:
            tag_to_remove = st.selectbox(
                "Remove a specific tag",
                options=list(st.session_state.modifications.keys()),
                key="remove_select"
            )
            if st.button("Remove Selected", use_container_width=True):
                del st.session_state.modifications[tag_to_remove]
                st.session_state.modified_bytes = None
                st.session_state.mod_results    = None
                st.session_state.queue_msg      = None
                st.rerun()

    with st.expander("View All Tags", expanded=False):
        def highlight_modified(row):
            if row["Tag"] in st.session_state.modifications:
                return ["background-color: #fff3cd"] * len(row)
            return [""] * len(row)
        st.dataframe(
            df.drop(columns=["Private"]).style.apply(highlight_modified, axis=1),
            use_container_width=True,
            height=400
        )

    # ── STEP 3: Apply & Download ─────────────────────
    st.header("③ Apply & Download")

    if not st.session_state.modifications:
        st.info("No modifications queued yet.")
    else:
        st.write(f"**{len(st.session_state.modifications)} tag(s)** queued for modification.")

        if st.session_state.upload_mode == "single":
            if st.button("🚀 Apply Changes", type="primary", use_container_width=True):
                with st.spinner("Processing..."):
                    modified_bytes, results = apply_modifications_to_ds(
                        st.session_state.ds,
                        st.session_state.modifications
                    )
                st.session_state.modified_bytes = modified_bytes
                st.session_state.mod_results    = results

            if st.session_state.mod_results:
                st.dataframe(
                    pd.DataFrame(st.session_state.mod_results),
                    use_container_width=True,
                    hide_index=True
                )

            if st.session_state.modified_bytes:
                st.download_button(
                    label="⬇️ Download Modified DICOM",
                    data=st.session_state.modified_bytes,
                    file_name=f"modified_{st.session_state.filename}",
                    mime="application/octet-stream",
                    use_container_width=True
                )

        else:
            st.info("All DICOM files in the ZIP will be modified with the same tag changes.")

            if st.button("🚀 Apply to All & Create ZIP", type="primary", use_container_width=True):
                with st.spinner("Processing ZIP... Please wait."):
                    result_bytes, all_results, summary = process_zip(
                        st.session_state.zip_bytes,
                        st.session_state.modifications
                    )
                # ✅ 핵심: spinner 블록 종료 직후 즉시 저장
                st.session_state.modified_bytes = result_bytes
                st.session_state.mod_results    = all_results
                st.session_state.summary        = summary
                # ✅ rerun 없음 — 같은 사이클에서 아래 코드가 바로 실행됨

            # ✅ session_state.summary 로만 판단 (zip_ready 플래그 불필요)
            if st.session_state.summary is not None:
                s = st.session_state.summary
                col_s1, col_s2, col_s3, col_s4 = st.columns(4)
                col_s1.metric("Total",     s["total"])
                col_s2.metric("Processed", s["success"])
                col_s3.metric("Skipped",   s["skipped"])
                col_s4.metric("Errors",    s["errors"])

                if s["success"] == 0:
                    st.error("No DICOM files were processed! Report를 확인해주세요.")

            if st.session_state.mod_results:
                with st.expander("View Modification Report", expanded=False):
                    st.dataframe(
                        pd.DataFrame(st.session_state.mod_results),
                        use_container_width=True,
                        height=400,
                        hide_index=True
                    )

            # ✅ Download 버튼
            if st.session_state.modified_bytes is not None:
                zip_name = st.session_state.filename.replace(".zip", "_modified.zip")
                st.success("ZIP is ready! Click below to download.")
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
    st.header("How to Use")
    st.markdown("""
    **Single File**
    1. Select Single DICOM mode
    2. Upload a .dcm file
    3. Select tag → Enter new value
    4. Queue Change → Apply → Download

    **Batch ZIP**
    1. Select Multiple DICOMs mode
    2. Upload a .zip file
    3. Select tag → Enter new value
    4. Queue Change → Apply to All → Download ZIP
    """)

    st.divider()
    st.header("Notes")
    st.warning(
        "Original files are never modified.\n\n"
        "Tags are applied to ALL DICOM files in ZIP.\n\n"
        "Do not upload real patient data to public deployments."
    )

    st.divider()
    st.header("Common Tags")
    tag_tab1, tag_tab2, tag_tab3 = st.tabs(["Standard", "AIRS Upload", "AIRS Recon"])

    with tag_tab1:
        standard_tags = [
            {"Tag": "(0020,000E)", "Keyword": "SeriesInstanceUID"},
            {"Tag": "(0020,000D)", "Keyword": "StudyInstanceUID"},
            {"Tag": "(0008,103E)", "Keyword": "SeriesDescription"},
            {"Tag": "(0010,0010)", "Keyword": "PatientName"},
            {"Tag": "(0008,0060)", "Keyword": "Modality"},
            {"Tag": "(2001,9000)", "Keyword": "Private Tag (Philips)"},
        ]
        for t in standard_tags:
            col_t, col_k = st.columns([2, 3])
            with col_t:
                st.code(t["Tag"], language=None)
            with col_k:
                st.caption(t["Keyword"])

    with tag_tab2:
        st.caption("AIRS Medical DCS Upload Tags")
        upload_tags = [
            {"Tag": "(00E1,1010)", "Name": "StudyId",              "VR": "LO", "Note": ""},
            {"Tag": "(00E1,1011)", "Name": "SeriesId",             "VR": "LO", "Note": ""},
            {"Tag": "(00E1,1012)", "Name": "ImageId",              "VR": "LO", "Note": ""},
            {"Tag": "(00E1,1014)", "Name": "UploadId",             "VR": "LO", "Note": ""},
            {"Tag": "(00E1,1015)", "Name": "DeviceId",             "VR": "LO", "Note": ""},
            {"Tag": "(00E1,1030)", "Name": "DispatchUnitId",       "VR": "LO", "Note": ""},
            {"Tag": "(00E1,1031)", "Name": "PostProcessingType",   "VR": "LO", "Note": "MIP/MPR/MinIP/ADC"},
            {"Tag": "(00E1,1032)", "Name": "SourceDispatchUnitId", "VR": "SH", "Note": ""},
            {"Tag": "(00E1,1033)", "Name": "ADCType",              "VR": "LO", "Note": "ADC"},
            {"Tag": "(00E1,1034)", "Name": "ADCNoiseThreshold",    "VR": "LO", "Note": "ADC, Diffusion"},
            {"Tag": "(00E1,1035)", "Name": "BValue",               "VR": "LO", "Note": "ADC, Diffusion"},
            {"Tag": "(00E1,1036)", "Name": "IsMarked",             "VR": "CS", "Note": "Mark only"},
            {"Tag": "(00E1,1037)", "Name": "NumberOfProjections",  "VR": "IS", "Note": "MIPComposing"},
            {"Tag": "(00E1,1038)", "Name": "RadialAngle",          "VR": "IS", "Note": "RadialMIP"},
            {"Tag": "(00E1,1039)", "Name": "Zoom",                 "VR": "LO", "Note": "RadialMIP"},
            {"Tag": "(00E1,1040)", "Name": "SliceOrder",           "VR": "LO", "Note": "RadialMIP"},
            {"Tag": "(00E1,1041)", "Name": "Orientation",          "VR": "LO", "Note": "ParallelRendering"},
            {"Tag": "(00E1,1042)", "Name": "Gap",                  "VR": "LO", "Note": "ParallelRendering"},
            {"Tag": "(00E1,1043)", "Name": "Thickness",            "VR": "LO", "Note": "ParallelRendering"},
            {"Tag": "(00E1,1044)", "Name": "CalculatedBvalue",     "VR": "SL", "Note": "Diffusion"},
            {"Tag": "(00E1,1045)", "Name": "PostprocessingMode",   "VR": "LO", "Note": "User_Defined_Mode"},
        ]
        for t in upload_tags:
            col_t, col_n, col_v = st.columns([2, 3, 1])
            with col_t:
                st.code(t["Tag"], language=None)
            with col_n:
                st.caption(f"**{t['Name']}**")
                if t["Note"]:
                    st.caption(t["Note"])
            with col_v:
                st.caption(f"`{t['VR']}`")

    with tag_tab3:
        st.caption("AIRS Medical Recon Output Tags")
        recon_tags = [
            {"Tag": "(00E1,1020)", "Name": "InputSnr",          "VR": "FL", "Note": ""},
            {"Tag": "(00E1,1021)", "Name": "OutputSnr",         "VR": "FL", "Note": ""},
            {"Tag": "(00E1,1022)", "Name": "DenoisingLevel",    "VR": "LO", "Note": "e.g. 4: 3.0"},
            {"Tag": "(00E1,1023)", "Name": "Sharpness",         "VR": "FL", "Note": ""},
            {"Tag": "(00E1,1024)", "Name": "ModelPath",         "VR": "OB", "Note": ""},
            {"Tag": "(00E1,1025)", "Name": "ModelHeader",       "VR": "LO", "Note": ""},
            {"Tag": "(00E1,1026)", "Name": "ModelVersion",      "VR": "LO", "Note": ""},
            {"Tag": "(00E1,1034)", "Name": "ADCNoiseThreshold", "VR": "LO", "Note": "value after ':'"},
            {"Tag": "(00E1,1035)", "Name": "BValue",            "VR": "LO", "Note": "applied B-values"},
        ]
        for t in recon_tags:
            col_t, col_n, col_v = st.columns([2, 3, 1])
            with col_t:
                st.code(t["Tag"], language=None)
            with col_n:
                st.caption(f"**{t['Name']}**")
                if t["Note"]:
                    st.caption(t["Note"])
            with col_v:
                st.caption(f"`{t['VR']}`")
