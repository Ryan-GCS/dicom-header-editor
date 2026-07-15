import streamlit as st
import pydicom
import pandas as pd
import io
from copy import deepcopy

# ── Page Config ──────────────────────────────────────
st.set_page_config(
    page_title="DICOM Header Editor",
    page_icon="🏥",
    layout="wide"
)

st.title("🏥 DICOM Header Editor")
st.caption("Upload a DICOM file, modify header tags, and download the result.")

# ── Utility Functions ────────────────────────────────
def parse_dicom(file_bytes: bytes):
    return pydicom.dcmread(io.BytesIO(file_bytes))

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

def apply_modifications(ds, modifications: dict):
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

                results.append({
                    "Tag":     tag_str,
                    "Keyword": ds_copy[tag].keyword,
                    "Before":  old_value,
                    "After":   new_value,
                    "Status":  "✅ Success"
                })
            else:
                results.append({
                    "Tag": tag_str, "Keyword": "-",
                    "Before": "-", "After": new_value,
                    "Status": "⚠️ Tag not found"
                })
        except Exception as e:
            results.append({
                "Tag": tag_str, "Keyword": "-",
                "Before": "-", "After": new_value,
                "Status": f"❌ Error: {e}"
            })

    output = io.BytesIO()
    ds_copy.save_as(output, write_like_original=True)
    return output.getvalue(), results

# ── Session State Init ───────────────────────────────
if "ds"            not in st.session_state: st.session_state.ds            = None
if "tags_df"       not in st.session_state: st.session_state.tags_df       = None
if "modifications" not in st.session_state: st.session_state.modifications = {}
if "filename"      not in st.session_state: st.session_state.filename      = ""
if "modified_bytes" not in st.session_state: st.session_state.modified_bytes = None
if "mod_results"   not in st.session_state: st.session_state.mod_results   = None

# ── STEP 1: File Upload ──────────────────────────────
st.header("① Upload DICOM File")

uploaded = st.file_uploader(
    "Upload a DICOM file (.dcm)",
    type=["dcm", "DCM"],
    help="If your file has no extension, rename it with .dcm before uploading."
)

if uploaded:
    file_bytes = uploaded.read()
    st.session_state.ds            = parse_dicom(file_bytes)
    st.session_state.tags_df       = extract_tags(st.session_state.ds)
    st.session_state.filename      = uploaded.name
    st.session_state.modifications = {}
    st.session_state.modified_bytes = None
    st.session_state.mod_results   = None
    st.success(f"✅ Loaded: `{uploaded.name}` — {len(st.session_state.tags_df)} tags found")

# ── STEP 2: Tag Viewer & Editor ──────────────────────
if st.session_state.ds is not None:
    st.header("② View & Edit Tags")

    # Search & Filter
    col1, col2 = st.columns([3, 1])
    with col1:
        search = st.text_input(
            "🔍 Search Tags",
            placeholder="e.g. SeriesInstanceUID or 0020,000E"
        )
    with col2:
        show_private = st.checkbox("Show Private Tags", value=True)

    df = pd.DataFrame(st.session_state.tags_df)
    if not show_private:
        df = df[df["Private"] == False]
    if search:
        mask = (
            df["Keyword"].str.contains(search, case=False, na=False) |
            df["Tag"].str.contains(search, case=False, na=False) |
            df["Value"].str.contains(search, case=False, na=False)
        )
        df = df[mask]

    st.caption(f"Showing {len(df)} tag(s)")

    # ── Tag Edit UI ──────────────────────────────────
    st.subheader("✏️ Edit a Tag")

    col_a, col_b, col_c = st.columns([2, 3, 1])
    with col_a:
        tag_options = df["Tag"].tolist()
        selected_tag = st.selectbox("Select tag to edit", tag_options)
    with col_b:
        if selected_tag:
            current_val = df[df["Tag"] == selected_tag]["Value"].values[0]
            default_val = st.session_state.modifications.get(selected_tag, current_val)
            new_value   = st.text_input("New value", value=default_val)
    with col_c:
        st.write("")
        st.write("")
        if st.button("➕ Add", use_container_width=True):
            if selected_tag and new_value is not None:
                st.session_state.modifications[selected_tag] = new_value
                st.session_state.modified_bytes = None  # reset download
                st.success(f"Added: {selected_tag}")

    # ── Pending Modifications ────────────────────────
    if st.session_state.modifications:
        st.subheader("📋 Pending Modifications")

        mod_data = []
        for tag, val in st.session_state.modifications.items():
            kw  = df[df["Tag"] == tag]["Keyword"].values
            kw  = kw[0] if len(kw) > 0 else "Unknown"
            ori = df[df["Tag"] == tag]["Value"].values
            ori = ori[0] if len(ori) > 0 else "-"
            mod_data.append({
                "Tag":      tag,
                "Keyword":  kw,
                "Original": ori,
                "New Value": val
            })

        st.dataframe(pd.DataFrame(mod_data), use_container_width=True, hide_index=True)

        col_del, col_tag_del = st.columns([2, 3])
        with col_del:
            if st.button("🗑️ Clear All", use_container_width=True):
                st.session_state.modifications  = {}
                st.session_state.modified_bytes = None
                st.session_state.mod_results    = None
                st.rerun()
        with col_tag_del:
            tag_to_remove = st.selectbox(
                "Remove a specific tag",
                options=list(st.session_state.modifications.keys()),
                key="remove_select"
            )
            if st.button("❌ Remove Selected", use_container_width=True):
                del st.session_state.modifications[tag_to_remove]
                st.session_state.modified_bytes = None
                st.rerun()

    # ── Full Tag Table ───────────────────────────────
    with st.expander("📄 View All Tags", expanded=False):
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
        st.info("No modifications added yet. Use the editor above to add changes.")
    else:
        st.write(f"**{len(st.session_state.modifications)} tag(s)** will be modified.")

        if st.button("🚀 Apply Modifications", type="primary", use_container_width=True):
            with st.spinner("Processing DICOM file..."):
                modified_bytes, results = apply_modifications(
                    st.session_state.ds,
                    st.session_state.modifications
                )
                st.session_state.modified_bytes = modified_bytes
                st.session_state.mod_results    = results

        # ── Result Report & Download ─────────────────
        if st.session_state.mod_results:
            st.subheader("📊 Modification Report")
            st.dataframe(
                pd.DataFrame(st.session_state.mod_results),
                use_container_width=True,
                hide_index=True
            )

        if st.session_state.modified_bytes:
            output_filename = f"modified_{st.session_state.filename}"
            st.download_button(
                label="⬇️ Download Modified DICOM",
                data=st.session_state.modified_bytes,
                file_name=output_filename,
                mime="application/octet-stream",
                use_container_width=True
            )

# ── Sidebar ──────────────────────────────────────────
with st.sidebar:
    st.header("📖 How to Use")
    st.markdown("""
    1. **Upload** a DICOM file
    2. **Search** for the tag you want to edit
    3. **Enter** a new value and click `Add`
    4. Repeat for multiple tags
    5. Click **Apply Modifications**
    6. **Download** the modified file
    """)

    st.divider()

    st.header("⚠️ Notes")
    st.warning("""
    - Original file is never modified
    - Be careful when editing Private Tags
    - Do not upload files with real patient data (PHI) to public deployments
    """)

    st.divider()

    st.header("🔧 Common Tags")
    st.code("""
(0020,000E) SeriesInstanceUID
(0020,000D) StudyInstanceUID
(0008,103E) SeriesDescription
(0010,0010) PatientName
(0008,0060) Modality
(2001,9000) Private Tag (Philips)
    """)
