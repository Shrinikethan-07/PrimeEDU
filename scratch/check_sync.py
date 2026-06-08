import os
import shutil
import filecmp

root_dir = r"c:\Users\HI\Desktop\PrimeEDU"
public_dir = r"c:\Users\HI\Desktop\PrimeEDU\public"

# Pairs to check (root_path, public_path)
sync_pairs = [
    ("app.js", "app.js"),
    ("dashboard.html", "dashboard.html"),
    ("journal.html", "journal.html"),
    ("leaderboard.html", "leaderboard.html"),
    ("modules.html", "modules.html"),
    ("recaps.html", "recaps.html"),
    ("style.css", "style.css"),
    ("teams.html", "teams.html"),
    ("timer.html", "timer.html"),
    ("login.html", "index.html"),  # login.html is root, index.html is public login
    ("admin.html", "admin.html"),   # admin.html is root and public/admin.html
    ("notifications.js", "notifications.js"),
    ("book-detail.html", "book-detail.html")
]

def sync_files():
    print("Checking file synchronization between root and public/...")
    any_diff = False
    for r_file, p_file in sync_pairs:
        r_path = os.path.join(root_dir, r_file)
        p_path = os.path.join(public_dir, p_file)
        
        # If public file does not exist, look if root file exists
        if not os.path.exists(p_path) and os.path.exists(r_path):
            print(f"Public file {p_path} does not exist. Copying from root...")
            shutil.copy2(r_path, p_path)
            any_diff = True
            continue

        # If root file does not exist, look if public file exists
        if not os.path.exists(r_path) and os.path.exists(p_path):
            print(f"Root file {r_path} does not exist. Copying from public...")
            shutil.copy2(p_path, r_path)
            any_diff = True
            continue

        if not os.path.exists(r_path) and not os.path.exists(p_path):
            print(f"Error: Neither root {r_file} nor public {p_file} exists!")
            continue
            
        # Compare
        if not filecmp.cmp(r_path, p_path, shallow=False):
            print(f"Difference detected between {r_file} and public/{p_file}.")
            # Let's check modification times to copy the newer one
            r_mtime = os.path.getmtime(r_path)
            p_mtime = os.path.getmtime(p_path)
            
            if r_mtime > p_mtime:
                print(f"Root file is newer. Copying to public/{p_file}...")
                shutil.copy2(r_path, p_path)
            else:
                print(f"Public file is newer. Copying to root/{r_file}...")
                shutil.copy2(p_path, r_path)
            any_diff = True
        else:
            print(f"Synced: {r_file} == public/{p_file}")
            
    if not any_diff:
        print("All files are perfectly in sync!")
    else:
        print("Synchronization finished successfully.")

if __name__ == "__main__":
    sync_files()
