import io
import re
from pathlib import Path

import pandas as pd
import streamlit as st

DEFAULT_COLUMNS = [
    'Fight Time', 'Avg TTK', 'Damage Done', 'Score', 'Scenario', 'Hash',
    'Game Version', 'Max FPS (config)', 'Sens Scale', 'Horiz Sens',
    'Vert Sens', 'FOV', 'filename', 'timestamp', 'Reloads', 'Challenge Start',
    'Pause Count', 'Pause Duration', 'Resolution', 'Avg FPS', 'Resolution Scale',
    'DPI', 'FOVScale', 'Time Remaining', 'Total Overshots', 'Hit Count', 'Miss Count'
]
MAX_UPLOAD_FILES = 500
DEFAULT_STATS_FOLDER = 'stats'


def parse_stats_file(file_name: str, content: bytes) -> pd.DataFrame:
    text = content.decode('utf-8', errors='replace')
    table_chunks = re.split(r'\r?\n\r?\n', text)

    if len(table_chunks) < 4:
        raise ValueError('File does not contain the expected CSV blocks')

    stats_df_temp = pd.read_csv(io.StringIO(table_chunks[2]))
    config_df_temp = pd.read_csv(io.StringIO(table_chunks[3]))

    stats_df_T = stats_df_temp.set_index(stats_df_temp.columns[0]).T
    config_df_T = config_df_temp.set_index(config_df_temp.columns[0]).T

    combined = pd.concat([stats_df_T.reset_index(drop=True), config_df_T.reset_index(drop=True)], axis=1)
    combined.columns = [col.rstrip(':') for col in combined.columns]
    combined['filename'] = file_name

    timestamp_match = re.search(r'(\d{4}\.\d{2}\.\d{2})-(\d{2}\.\d{2}\.\d{2})', file_name)
    if timestamp_match:
        date_part = timestamp_match.group(1)
        time_part = timestamp_match.group(2)
        datetime_str = date_part.replace('.', '-') + ' ' + time_part.replace('.', ':')
        combined['timestamp'] = pd.to_datetime(datetime_str, errors='coerce')
    else:
        combined['timestamp'] = pd.NaT

    return combined


def parse_local_folder(folder_path: str) -> tuple[list[pd.DataFrame], list[str]]:
    path = Path(folder_path).expanduser()
    if not path.exists() or not path.is_dir():
        raise ValueError(f'Folder not found: {path}')

    csv_files = sorted(path.glob('*.csv'))
    if not csv_files:
        raise ValueError(f'No CSV files found in: {path}')

    dataframes = []
    errors = []
    for file_path in csv_files:
        with file_path.open('rb') as f:
            try:
                dataframes.append(parse_stats_file(file_path.name, f.read()))
            except Exception as exc:
                errors.append(f'{file_path.name}: {exc}')
    return dataframes, errors


def build_final_dataframe(dataframes: list[pd.DataFrame]) -> pd.DataFrame:
    if not dataframes:
        raise ValueError('No valid stats files were provided')
    final_df = pd.concat(dataframes, ignore_index=True)
    existing_cols = [col for col in DEFAULT_COLUMNS if col in final_df.columns]
    final_df_cleaned = final_df[existing_cols]
    return final_df_cleaned


def main() -> None:
    st.set_page_config(page_title='KovaaK Stats Concatenator', layout='wide')
    st.title('KovaaK Stats Concatenator')

    st.markdown(
        'For large batches (10k+ files), use a local folder path. Upload mode is only for smaller file sets.'
    )

    mode = st.radio('Processing mode', ['Local folder', 'Upload CSV files'], index=0, horizontal=True)

    processed = []
    errors = []

    local_errors = []
    if mode == 'Local folder':
        folder_path = st.text_input('Local stats folder path', value=DEFAULT_STATS_FOLDER)
        process_button = st.button('Process folder')

        if process_button:
            try:
                processed, local_errors = parse_local_folder(folder_path)
            except Exception as exc:
                st.error(f'Folder processing failed: {exc}')
                return
    else:
        uploaded = st.file_uploader(
            'Upload CSV files from the stats folder',
            type='csv',
            accept_multiple_files=True,
        )

        if not uploaded:
            st.info('Upload files to begin processing.')
            return

        if len(uploaded) > MAX_UPLOAD_FILES:
            st.error(f'Too many CSV files uploaded ({len(uploaded)} > {MAX_UPLOAD_FILES}). Use Local folder mode instead.')
            return

        for uploaded_file in uploaded:
            try:
                processed.append(parse_stats_file(uploaded_file.name, uploaded_file.read()))
            except Exception as exc:
                errors.append(f'{uploaded_file.name}: {exc}')

    if mode == 'Local folder' and local_errors:
        errors.extend(local_errors)

    if errors:
        st.error('Some files failed to process:')
        for error in errors:
            st.write(f'- {error}')

    if not processed:
        if mode == 'Local folder':
            st.warning('No files were processed from the folder.')
        else:
            st.warning('No valid files were uploaded.')
        return

    with st.spinner('Merging data...'):
        final_df = build_final_dataframe(processed)

    total_attempted = len(processed) + len(errors)
    st.success(f'Processed {len(processed)} file(s), {len(errors)} errors, {total_attempted} attempted.')
    st.dataframe(final_df.head(20))

    csv_bytes = final_df.to_csv(index=False).encode('utf-8')
    st.download_button(
        'Download merged CSV',
        data=csv_bytes,
        file_name='all_stats_combined_cleaned.csv',
        mime='text/csv',
    )


if __name__ == '__main__':
    main()
