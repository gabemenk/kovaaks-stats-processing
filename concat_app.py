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


def choose_local_folder(initial_dir: str = DEFAULT_STATS_FOLDER) -> str | None:
    try:
        import tkinter as tk
        from tkinter import filedialog
    except ImportError:
        return None

    root = tk.Tk()
    root.withdraw()
    root.attributes('-topmost', True)
    folder = filedialog.askdirectory(initialdir=initial_dir, title='Select stats folder')
    root.destroy()
    return folder or None


def build_final_dataframe(dataframes: list[pd.DataFrame]) -> pd.DataFrame:
    if not dataframes:
        raise ValueError('No valid stats files were provided')
    final_df = pd.concat(dataframes, ignore_index=True)
    existing_cols = [col for col in DEFAULT_COLUMNS if col in final_df.columns]
    final_df_cleaned = final_df[existing_cols]
    return final_df_cleaned


def main() -> None:
    st.set_page_config(page_title='Kovaak\'s Stats Files Concatenator', layout='wide')
    st.title('Kovaak\'s Stats Files Concatenator')

    st.markdown(
        'For large batches, select a local folder by browsing or pasting the path. Upload mode is available for small file sets.'
    )

    mode = st.radio('Processing mode', ['Local folder', 'Upload CSV files'], index=0, horizontal=True)

    processed = []
    errors = []

    local_errors = []
    if mode == 'Local folder':
        if 'local_folder_path_input' not in st.session_state:
            st.session_state.local_folder_path_input = DEFAULT_STATS_FOLDER

        folder_path = st.text_input(
            'Local stats folder path',
            value=st.session_state.local_folder_path_input,
            key='local_folder_path_input',
        )

        def browse_folder_callback() -> None:
            selected_folder = choose_local_folder(st.session_state.local_folder_path_input)
            if selected_folder:
                st.session_state.local_folder_path_input = selected_folder

        browse_button, process_button = st.columns([1, 1])
        with browse_button:
            st.button('Browse folder', on_click=browse_folder_callback)
        with process_button:
            if st.button('Process folder'):
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

        for uploaded_file in uploaded:
            try:
                processed.append(parse_stats_file(uploaded_file.name, uploaded_file.read()))
            except Exception as exc:
                errors.append(f'{uploaded_file.name}: {exc}')

    if mode == 'Local folder' and local_errors:
        errors.extend(local_errors)


    if not processed:
        if mode == 'Local folder':
            st.warning('No files were processed from the folder.')
        else:
            st.warning('No valid files were uploaded.')
        return

    with st.spinner('Merging data.'):
        final_df = build_final_dataframe(processed)
        final_df = final_df.sort_values('timestamp', ascending=False, na_position='last').reset_index(drop=True)

    total_attempted = len(processed) + len(errors)
    st.success(f'Processed {len(processed)} file(s), {len(errors)} errors, {total_attempted} attempted.')
    st.dataframe(final_df)

    csv_bytes = final_df.to_csv(index=False).encode('utf-8')
    st.download_button(
        'Download merged CSV',
        data=csv_bytes,
        file_name='all_stats_combined_cleaned.csv',
        mime='text/csv',
    )


if __name__ == '__main__':
    main()
