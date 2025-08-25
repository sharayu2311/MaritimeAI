import pandas as pd

INPUT_CSV = "ports.csv"
OUTPUT_CSV = "normalized_ports.csv"

# Read robustly (semicolon-separated, skip broken lines)
df = pd.read_csv(INPUT_CSV, delimiter=";", on_bad_lines="skip")

# Keep only relevant columns
df = df[["Name", "Coordinates"]].dropna()

# Normalize names (lowercase, stripped, no extra spaces)
df["normalized"] = df["Name"].str.lower().str.strip()

# Save
df.to_csv(OUTPUT_CSV, index=False)

print(f"✅ Normalized {len(df)} ports → {OUTPUT_CSV}")
