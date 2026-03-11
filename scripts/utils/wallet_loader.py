import csv
import os

def load_wallets_from_csv(filepath: str) -> list:
    """Load wallets from a CSV file."""
    if not os.path.exists(filepath):
        print(f"Warning: {filepath} not found.")
        return []
        
    wallets = []
    with open(filepath, mode='r') as file:
        reader = csv.DictReader(file)
        for row in reader:
             chains = row['chains'].split('|')
             wallets.append({
                 'address': row['address'],
                 'cluster_id': int(row['cluster_id']),
                 'chains': chains
             })
    return wallets
