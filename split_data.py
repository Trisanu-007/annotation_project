#!/usr/bin/env python3
"""
Script to split the parquet data into 10 user-specific JSON files.
Each user gets 20 non-overlapping samples (200 samples total).
"""

import pandas as pd
import json
import os

def split_data_for_users(input_file, output_dir='user_data', num_users=10, samples_per_user=20):
    """
    Split the parquet file into separate JSON files for each user.
    
    Args:
        input_file: Path to the input parquet file
        output_dir: Directory to store user-specific data files
        num_users: Number of users (default: 10)
        samples_per_user: Number of samples per user (default: 20)
    """
    # Read the parquet file
    print(f"Reading data from {input_file}...")
    df = pd.read_parquet(input_file)
    
    total_samples = num_users * samples_per_user
    print(f"Total rows in file: {len(df)}")
    print(f"Required samples: {total_samples}")
    
    if len(df) < total_samples:
        print(f"Warning: File has only {len(df)} rows, but {total_samples} required!")
        return
    
    # Take first 200 rows (or adjust as needed)
    data_subset = df.head(total_samples)
    
    # Create output directory if it doesn't exist
    os.makedirs(output_dir, exist_ok=True)
    
    # Split data for each user
    for user_id in range(1, num_users + 1):
        start_idx = (user_id - 1) * samples_per_user
        end_idx = start_idx + samples_per_user
        
        user_data = data_subset.iloc[start_idx:end_idx]
        
        # Convert to list of dictionaries
        user_records = user_data.to_dict('records')
        
        # Save to JSON file
        output_file = os.path.join(output_dir, f'user_{user_id}_data.json')
        with open(output_file, 'w') as f:
            json.dump(user_records, f, indent=2)
        
        print(f"Created {output_file} with {len(user_records)} samples")
    
    # Create a metadata file to track user assignments
    metadata = {
        'num_users': num_users,
        'samples_per_user': samples_per_user,
        'total_samples': total_samples,
        'user_assignments': {
            f'user_{i}': {
                'file': f'user_{i}_data.json',
                'start_idx': (i-1) * samples_per_user,
                'end_idx': i * samples_per_user
            }
            for i in range(1, num_users + 1)
        }
    }
    
    metadata_file = os.path.join(output_dir, 'metadata.json')
    with open(metadata_file, 'w') as f:
        json.dump(metadata, f, indent=2)
    
    print(f"\nMetadata saved to {metadata_file}")
    print(f"All user data files created successfully in {output_dir}/")

if __name__ == '__main__':
    input_file = 'alice_test_depth0-50_complete.parquet'
    split_data_for_users(input_file)
