import streamlit as st
from sqlalchemy.exc import SQLAlchemyError

from farm.auth import require
from farm.db import ROOT
from farm.fwi import FILES, SOURCE_COMMIT, SOURCE_URL, datasets, import_fwi, prepare_import, read_research


def render_fwi(engine, actor):
    require(engine, actor, "import")
    st.title("FWI research data")
    st.markdown(f"Source: [Fish Welfare Initiative — India]({SOURCE_URL}) · CC-BY-4.0")
    st.info("Research snapshots are kept separate from your farm inventory. Visit-level deaths and feed do not establish daily consumption or a complete stocking cycle, so FCR and live stock are not inferred.")
    with st.expander("Import a dataset snapshot"):
        release = st.text_input("Release label", value="FWI v3.0.0 · August 2026")
        uploads = st.file_uploader("Upload all four FWI CSV files", type="csv", accept_multiple_files=True)
        local = ROOT / "data" / "fwi-source"
        use_local = st.checkbox("Use the downloaded public snapshot", value=not bool(uploads),
                                disabled=not all((local / name).exists() for name in FILES))
        files = {item.name: item.getvalue() for item in uploads}
        if use_local and all((local / name).exists() for name in FILES):
            files = {name: (local / name).read_bytes() for name in FILES}
            st.caption(f"Downloaded at repository commit {SOURCE_COMMIT}.")
        if files:
            try:
                prepared = prepare_import(files, release)
                st.json(prepared["manifest"])
                if st.button("Import this snapshot", type="primary"):
                    dataset_id, created = import_fwi(engine, actor, prepared)
                    st.success(f"Snapshot {dataset_id} {'imported' if created else 'already exists; no duplicate rows added'}.")
            except (ValueError, PermissionError) as exc:
                st.error(str(exc))
            except SQLAlchemyError:
                st.error("Import failed or a concurrent import already completed. Refresh and inspect the snapshot list.")
    versions = datasets(engine, actor)
    if versions.empty:
        st.info("Import a snapshot to browse the source records and use FWI trends in Advanced insights.")
        return
    labels = {int(r.id): f"{r.release} · {str(r.digest)[:8]}" for r in versions.itertuples()}
    dataset_id = st.selectbox("Snapshot", list(labels), format_func=labels.get)
    file = st.selectbox("Source table", list(FILES))
    frame = read_research(engine, actor, dataset_id, file)
    st.caption(f"{len(frame):,} source rows · original values preserved · source_row is the CSV record number including the header.")
    if not frame.empty:
        ids = st.multiselect("Filter pond IDs", sorted(frame.pond_id.unique()))
        if ids:
            frame = frame[frame.pond_id.isin(ids)]
        st.dataframe(frame, hide_index=True, width="stretch")
    with st.expander("Import provenance and data quality"):
        st.json(versions[versions.id == dataset_id].iloc[0].manifest)
