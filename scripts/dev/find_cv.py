import glob
import os
import shutil

downloads_path = os.path.expanduser("~/Downloads")
patterns = [
    os.path.join(downloads_path, "*Haputhanthri*.pdf"),
    os.path.join(downloads_path, "*CV*.pdf"),
    os.path.join(downloads_path, "*resume*.pdf"),
]

all_files = []
for p in patterns:
    all_files.extend(glob.glob(p))

if all_files:
    # Sort by modification time descending
    all_files = sorted(list(set(all_files)), key=os.path.getmtime, reverse=True)
    latest = all_files[0]
    os.makedirs("data", exist_ok=True)
    dest = os.path.join("data", "cv.pdf")
    shutil.copy2(latest, dest)
    print(f"Copied latest CV from '{latest}' to '{dest}' (size: {os.path.getsize(dest)} bytes)")
else:
    print("No CV found in Downloads.")
