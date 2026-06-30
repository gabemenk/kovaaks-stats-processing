import io
import re
import datetime
from pathlib import Path

import pandas as pd
import streamlit as st
import plotly.graph_objects as go

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


def build_final_dataframe(dataframes: list[pd.DataFrame], existing_df: pd.DataFrame | None = None) -> pd.DataFrame:
    if not dataframes:
        raise ValueError('No valid stats files were provided')

    if existing_df is None:
        combined_df = pd.concat(dataframes, ignore_index=True)
    else:
        existing_df_cleaned = existing_df.copy()
        if 'timestamp' in existing_df_cleaned.columns:
            existing_df_cleaned['timestamp'] = pd.to_datetime(existing_df_cleaned['timestamp'], errors='coerce')

        combined_df = pd.concat([existing_df_cleaned, *dataframes], ignore_index=True, sort=False)

    existing_cols = [col for col in DEFAULT_COLUMNS if col in combined_df.columns]
    final_df_cleaned = combined_df[existing_cols]

    # create a new column for accuracy
    for column_name in ['Hit Count', 'Miss Count']:
        final_df_cleaned[column_name] = pd.to_numeric(final_df_cleaned[column_name], errors='coerce')

    total_shots = final_df_cleaned['Hit Count'] + final_df_cleaned['Miss Count']
    accuracy = (final_df_cleaned['Hit Count'] / total_shots.replace(0, pd.NA)) * 100
    final_df_cleaned['accuracy'] = accuracy.round(2)

    # reorder columns
    order = [
        'Scenario', 'timestamp', 'Score', 'accuracy', 'Hit Count', 'Miss Count',   
        'DPI', 'Sens Scale', 'Horiz Sens', 'Vert Sens'
    ]
    remaining_cols = [col for col in final_df_cleaned.columns if col not in order]
    final_df_cleaned = final_df_cleaned[order + remaining_cols]

    return final_df_cleaned


def main() -> None:
    st.set_page_config(page_title='Kovaak\'s Stats Files Concatenator', layout='wide')
    st.title('Kovaak\'s Stats Files Concatenator')

    st.markdown(
        'Use the create a CSV mode to create a new CSV file by selecting your local kovaaks stats folder. Use the append mode to add data to an existing CSV file.'
    )
    st.markdown(
        'Append mode avoids reprocessing the entire folder, saving time, but is not recommended for large additional data.'
    )

    mode = st.radio(
        'Processing mode',
        ['Create a new CSV', 'Append to existing CSV'],
        index=0,
        horizontal=True,
    )

    processed = []
    errors = []
    local_errors = []
    existing_df = None

    if mode == 'Create a new CSV':
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
            if st.button('Create new CSV'):
                try:
                    processed, local_errors = parse_local_folder(folder_path)
                except Exception as exc:
                    st.error(f'Folder processing failed: {exc}')
                    return
    else:
        existing_csv = st.file_uploader('Existing CSV file to append to', type='csv', accept_multiple_files=False)
        uploaded = st.file_uploader(
            'Upload stats files to parse and append (optional)',
            type='csv',
            accept_multiple_files=True,
        )

        if existing_csv is None:
            st.info('Upload an existing CSV file to append to.')
            return

        try:
            existing_df = pd.read_csv(existing_csv)
        except Exception as exc:
            st.error(f'Failed to read the existing CSV: {exc}')
            return

        for uploaded_file in uploaded:
            try:
                processed.append(parse_stats_file(uploaded_file.name, uploaded_file.read()))
            except Exception as exc:
                errors.append(f'{uploaded_file.name}: {exc}')

    if mode == 'Create a new CSV' and local_errors:
        errors.extend(local_errors)

    if not processed:
        if mode == 'Create a new CSV':
            st.warning('No files were processed from the folder.')
            return
        elif existing_df is not None:
            final_df = existing_df
        else:
            st.warning('No files to process.')
            return
    else:
        with st.spinner('Merging data.'):
            if mode == 'Create a new CSV':
                final_df = build_final_dataframe(processed)
            else:
                final_df = build_final_dataframe(processed, existing_df)
            final_df = final_df.sort_values('timestamp', ascending=False, na_position='last').reset_index(drop=True)

    total_attempted = len(processed) + len(errors)
    st.success(f'Processed {len(processed)} file(s), {len(errors)} errors, {total_attempted} attempted.')
    st.dataframe(final_df)

    csv_bytes = final_df.to_csv(index=False).encode('utf-8')
    output_name = 'all_stats_combined_cleaned.csv' if mode == 'Create a new CSV' else 'all_stats_combined_appended.csv'
    st.download_button(
        'Download merged CSV',
        data=csv_bytes,
        file_name=output_name,
        mime='text/csv',
    )

    st.markdown('---')
    filter_mode = st.radio(
        'Analysis mode',
        ['Simple Filter', 'Comparison Tool'],
        index=0,
        horizontal=True,
    )

    final_df['timestamp'] = pd.to_datetime(final_df['timestamp'], errors='coerce')

    if filter_mode == 'Simple Filter':
        st.subheader('Filtered View by Date Range')

        col1, col2, col3, col4 = st.columns(4)
        with col1:
            start_date = st.date_input('Start date', value=datetime.date.today())
        with col2:
            start_time_str = st.text_input('Start time (HH:MM:SS)', value='00:00:00')
        with col3:
            end_date = st.date_input('End date', value=datetime.date.today())
        with col4:
            end_time_str = st.text_input('End time (HH:MM:SS)', value='23:59:59')

        try:
            start_time_parts = list(map(int, start_time_str.split(':')))
            start_time = datetime.time(start_time_parts[0], start_time_parts[1], start_time_parts[2] if len(start_time_parts) > 2 else 0)
        except (ValueError, IndexError):
            st.warning('Invalid start time format. Use HH:MM:SS')
            start_time = datetime.time(0, 0, 0)

        try:
            end_time_parts = list(map(int, end_time_str.split(':')))
            end_time = datetime.time(end_time_parts[0], end_time_parts[1], end_time_parts[2] if len(end_time_parts) > 2 else 0)
        except (ValueError, IndexError):
            st.warning('Invalid end time format. Use HH:MM:SS')
            end_time = datetime.time(23, 59, 59)

        start_datetime = pd.Timestamp(start_date.year, start_date.month, start_date.day, start_time.hour, start_time.minute, start_time.second).tz_localize(None)
        end_datetime = pd.Timestamp(end_date.year, end_date.month, end_date.day, end_time.hour, end_time.minute, end_time.second).tz_localize(None)

        filtered_df = final_df[(final_df['timestamp'] >= start_datetime) & (final_df['timestamp'] <= end_datetime)]

        ordered_columns = [
            'Scenario', 'timestamp', 'Score', 'accuracy', 'Hit Count', 'Miss Count',   
            'DPI', 'Sens Scale', 'Horiz Sens', 'Vert Sens'
        ]
        available_ordered_columns = [col for col in ordered_columns if col in filtered_df.columns]
        filtered_df_display = filtered_df[available_ordered_columns]

        st.dataframe(filtered_df_display)
        st.write(f'Showing {len(filtered_df_display)} records in the selected date range.')

        st.markdown('---')
        st.subheader('Score Progression by Scenario')

        unique_scenarios = sorted(filtered_df['Scenario'].dropna().unique())
        if unique_scenarios:
            selected_scenario = st.selectbox(
                'Select a scenario',
                unique_scenarios,
                index=0
            )

            scenario_df = filtered_df[filtered_df['Scenario'] == selected_scenario].copy()
            scenario_df = scenario_df.sort_values('timestamp').reset_index(drop=True)
            scenario_df['Run #'] = range(1, len(scenario_df) + 1)

            if len(scenario_df) > 0:
                chart_data = scenario_df[['Run #', 'Score']].copy()
                chart_data['Score'] = pd.to_numeric(chart_data['Score'], errors='coerce')
                st.line_chart(chart_data.set_index('Run #'))
                st.write(f'{len(scenario_df)} runs of "{selected_scenario}" in the selected time range.')
            else:
                st.info(f'No data for scenario "{selected_scenario}" in the selected time range.')
        else:
            st.info('No scenarios available in the selected date range.')

    else:
        st.subheader('Comparison Tool')

        col_name_a, col_name_b = st.columns(2)
        with col_name_a:
            range_a_name = st.text_input(
            'Range A name',
            value='Range A',
            key='range_a_name'
        )
        with col_name_b:
            range_b_name = st.text_input(
            'Range B name',
            value='Range B',
            key='range_b_name'
        )

        col1, col2 = st.columns(2)
        
        col1, col2 = st.columns(2)
        with col1:
            st.write('**Range A**')
            col_a1, col_a2, col_a3, col_a4 = st.columns(4)
            with col_a1:
                start_date_a = st.date_input('Start date A', value=datetime.date.today(), key='start_date_a')
            with col_a2:
                start_time_str_a = st.text_input('Start time A (HH:MM:SS)', value='00:00:00', key='start_time_a')
            with col_a3:
                end_date_a = st.date_input('End date A', value=datetime.date.today(), key='end_date_a')
            with col_a4:
                end_time_str_a = st.text_input('End time A (HH:MM:SS)', value='23:59:59', key='end_time_a')

        with col2:
            st.write('**Range B**')
            col_b1, col_b2, col_b3, col_b4 = st.columns(4)
            with col_b1:
                start_date_b = st.date_input('Start date B', value=datetime.date.today(), key='start_date_b')
            with col_b2:
                start_time_str_b = st.text_input('Start time B (HH:MM:SS)', value='00:00:00', key='start_time_b')
            with col_b3:
                end_date_b = st.date_input('End date B', value=datetime.date.today(), key='end_date_b')
            with col_b4:
                end_time_str_b = st.text_input('End time B (HH:MM:SS)', value='23:59:59', key='end_time_b')

        try:
            start_time_parts_a = list(map(int, start_time_str_a.split(':')))
            start_time_a = datetime.time(start_time_parts_a[0], start_time_parts_a[1], start_time_parts_a[2] if len(start_time_parts_a) > 2 else 0)
        except (ValueError, IndexError):
            st.warning('Invalid Range A start time format. Use HH:MM:SS')
            start_time_a = datetime.time(0, 0, 0)

        try:
            end_time_parts_a = list(map(int, end_time_str_a.split(':')))
            end_time_a = datetime.time(end_time_parts_a[0], end_time_parts_a[1], end_time_parts_a[2] if len(end_time_parts_a) > 2 else 0)
        except (ValueError, IndexError):
            st.warning('Invalid Range A end time format. Use HH:MM:SS')
            end_time_a = datetime.time(23, 59, 59)

        try:
            start_time_parts_b = list(map(int, start_time_str_b.split(':')))
            start_time_b = datetime.time(start_time_parts_b[0], start_time_parts_b[1], start_time_parts_b[2] if len(start_time_parts_b) > 2 else 0)
        except (ValueError, IndexError):
            st.warning('Invalid Range B start time format. Use HH:MM:SS')
            start_time_b = datetime.time(0, 0, 0)

        try:
            end_time_parts_b = list(map(int, end_time_str_b.split(':')))
            end_time_b = datetime.time(end_time_parts_b[0], end_time_parts_b[1], end_time_parts_b[2] if len(end_time_parts_b) > 2 else 0)
        except (ValueError, IndexError):
            st.warning('Invalid Range B end time format. Use HH:MM:SS')
            end_time_b = datetime.time(23, 59, 59)

        start_datetime_a = pd.Timestamp(start_date_a.year, start_date_a.month, start_date_a.day, start_time_a.hour, start_time_a.minute, start_time_a.second).tz_localize(None)
        end_datetime_a = pd.Timestamp(end_date_a.year, end_date_a.month, end_date_a.day, end_time_a.hour, end_time_a.minute, end_time_a.second).tz_localize(None)

        start_datetime_b = pd.Timestamp(start_date_b.year, start_date_b.month, start_date_b.day, start_time_b.hour, start_time_b.minute, start_time_b.second).tz_localize(None)
        end_datetime_b = pd.Timestamp(end_date_b.year, end_date_b.month, end_date_b.day, end_time_b.hour, end_time_b.minute, end_time_b.second).tz_localize(None)

        filtered_df_a = final_df[(final_df['timestamp'] >= start_datetime_a) & (final_df['timestamp'] <= end_datetime_a)]
        filtered_df_b = final_df[(final_df['timestamp'] >= start_datetime_b) & (final_df['timestamp'] <= end_datetime_b)]

        ordered_columns = [
            'Scenario', 'timestamp', 'Score', 'accuracy', 'Hit Count', 'Miss Count',   
            'DPI', 'Sens Scale', 'Horiz Sens', 'Vert Sens'
        ]
        available_ordered_columns = [col for col in ordered_columns if col in filtered_df_a.columns]
        filtered_df_a_display = filtered_df_a[available_ordered_columns]
        filtered_df_b_display = filtered_df_b[available_ordered_columns]

        st.write(f'**{range_a_name} Data**')
        st.dataframe(filtered_df_a_display)
        st.write(f'Showing {len(filtered_df_a_display)} records.')

        st.write(f'**{range_b_name} Data**')
        st.dataframe(filtered_df_b_display)
        st.write(f'Showing {len(filtered_df_b_display)} records.')

        st.markdown('---')
        st.subheader('Score Comparison Graph by Scenario')

        unique_scenarios_a = sorted(filtered_df_a['Scenario'].dropna().unique())
        unique_scenarios_b = sorted(filtered_df_b['Scenario'].dropna().unique())
        common_scenarios = sorted(set(unique_scenarios_a) & set(unique_scenarios_b))

        if common_scenarios:
            selected_scenario = st.selectbox(
                'Select a scenario to compare',
                common_scenarios,
                index=0,
                key='comparison_scenario'
            )

            scenario_df_a = filtered_df_a[filtered_df_a['Scenario'] == selected_scenario].copy()
            scenario_df_a = scenario_df_a.sort_values('timestamp').reset_index(drop=True)
            scenario_df_a['Run #'] = range(1, len(scenario_df_a) + 1)
            scenario_df_a['Range'] = range_a_name

            scenario_df_b = filtered_df_b[filtered_df_b['Scenario'] == selected_scenario].copy()
            scenario_df_b = scenario_df_b.sort_values('timestamp').reset_index(drop=True)
            scenario_df_b['Run #'] = range(1, len(scenario_df_b) + 1)
            scenario_df_b['Range'] = range_b_name

            if len(scenario_df_a) > 0 or len(scenario_df_b) > 0:
                scenario_df_a['Score'] = pd.to_numeric(scenario_df_a['Score'], errors='coerce')
                scenario_df_b['Score'] = pd.to_numeric(scenario_df_b['Score'], errors='coerce')

                comparison_data = pd.DataFrame()
                if len(scenario_df_a) > 0:
                    comparison_data = pd.concat([comparison_data, scenario_df_a[['Run #', 'Score', 'Range']]])
                if len(scenario_df_b) > 0:
                    comparison_data = pd.concat([comparison_data, scenario_df_b[['Run #', 'Score', 'Range']]])

                if len(comparison_data) > 0:
                    fig = go.Figure()
                    
                    if len(scenario_df_a) > 0:
                        fig.add_trace(go.Scatter(
                            x=scenario_df_a['Run #'],
                            y=scenario_df_a['Score'],
                            mode='lines',
                            name=range_a_name,
                            line=dict(color='#FF6B6B', width=3)
                        ))
                    
                    if len(scenario_df_b) > 0:
                        fig.add_trace(go.Scatter(
                            x=scenario_df_b['Run #'],
                            y=scenario_df_b['Score'],
                            mode='lines',
                            name=range_b_name,
                            line=dict(color='#4169E1', width=3)
                        ))
                    
                    fig.update_layout(
                        title=f'Score Progression: {selected_scenario}',
                        xaxis_title='Run #',
                        yaxis_title='Score',
                        hovermode='x unified',
                        height=500
                    )
                    st.plotly_chart(fig, use_container_width=True)
                    summary_col1, summary_col2 = st.columns(2)

                    with summary_col1:
                        if len(scenario_df_a) > 0:
                            avg_score_a = scenario_df_a['Score'].mean()
                            avg_accuracy_a = pd.to_numeric(
                                scenario_df_a['accuracy'],
                                errors='coerce'
                            ).mean()

                            st.markdown(f"""
                    **{range_a_name}**
                    - Runs: **{len(scenario_df_a)}**
                    - Average Score: **{avg_score_a:.2f}**
                    - Average Accuracy: **{avg_accuracy_a:.2f}%**
                    """)

                    with summary_col2:
                        if len(scenario_df_b) > 0:
                            avg_score_b = scenario_df_b['Score'].mean()
                            avg_accuracy_b = pd.to_numeric(
                                scenario_df_b['accuracy'],
                                errors='coerce'
                            ).mean()

                            st.markdown(f"""
                    **{range_b_name}**
                    - Runs: **{len(scenario_df_b)}**
                    - Average Score: **{avg_score_b:.2f}**
                    - Average Accuracy: **{avg_accuracy_b:.2f}%**
                    """)
            else:
                st.info(f'No data for scenario "{selected_scenario}" in the selected ranges.')
        else:
            st.info('No common scenarios between Range A and Range B.')


if __name__ == '__main__':
    main()
