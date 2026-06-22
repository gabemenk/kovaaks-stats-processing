import pandas as pd
import io
import glob
import os

# get all CSV files in the stats folder
stats_dir = 'stats'
all_files = sorted(glob.glob(os.path.join(stats_dir, '*.csv')))
print(f"Found {len(all_files)} files to process")

# Process all files and combine into one dataframe
import re
from datetime import datetime

all_data = []

for file_path in all_files:
    try:
        # Open and split the file contents by empty lines
        with open(file_path) as f:
            table_chunks = f.read().split("\n\n")
        
        # Load each block into its own DataFrame
        stats_df_temp = pd.read_csv(io.StringIO(table_chunks[2]))
        config_df_temp = pd.read_csv(io.StringIO(table_chunks[3]))
        
        # Transpose both dataframes
        stats_df_T = stats_df_temp.set_index(stats_df_temp.columns[0]).T
        config_df_T = config_df_temp.set_index(config_df_temp.columns[0]).T
        
        # Combine stats and config
        combined = pd.concat([stats_df_T.reset_index(drop=True), config_df_T.reset_index(drop=True)], axis=1)
        
        # remove the character ':' from every column name
        combined.columns = [col.rstrip(':') for col in combined.columns]
        
        # Add the filename as metadata
        filename = os.path.basename(file_path)
        combined['filename'] = filename
        
        # Extract timestamp from filename (format: YYYY.MM.DD-HH.MM.SS)
        timestamp_match = re.search(r'(\d{4}\.\d{2}\.\d{2})-(\d{2}\.\d{2}\.\d{2})', filename)
        if timestamp_match:
            date_part = timestamp_match.group(1)  # YYYY.MM.DD
            time_part = timestamp_match.group(2)  # HH.MM.SS
            # Convert dots to colons/dashes for datetime parsing
            datetime_str = date_part.replace('.', '-') + ' ' + time_part.replace('.', ':')
            combined['timestamp'] = pd.to_datetime(datetime_str)
        else:
            combined['timestamp'] = pd.NaT
        
        all_data.append(combined)
        print(f"Processed: {filename}")
        
    except Exception as e:
        print(f"Error with {os.path.basename(file_path)}: {str(e)}")

# Combine all dataframes into one
final_df = pd.concat(all_data, ignore_index=True)
print(f"\nTotal records: {len(final_df)}")

final_df_cleaned = final_df[['Fight Time', 'Avg TTK', 'Damage Done', 
       'Score', 'Scenario', 'Hash', 'Game Version', 'Max FPS (config)',
       'Sens Scale', 'Horiz Sens', 'Vert Sens', 'FOV',
       'filename', 'timestamp',
       'Reloads', 'Challenge Start', 'Pause Count', 'Pause Duration',
       'Resolution', 'Avg FPS', 'Resolution Scale', 'DPI', 'FOVScale',
       'Time Remaining', 'Total Overshots', 'Hit Count', 'Miss Count',
       ]]

final_df_cleaned.to_csv('all_stats_combined_cleaned.csv', index=False)