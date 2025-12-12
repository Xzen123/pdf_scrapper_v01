import os
import requests
from bs4 import BeautifulSoup
from urllib.parse import urljoin, urlparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from tqdm import tqdm

# --- CONFIGURATION ---
MAX_THREADS = 5  # Number of simultaneous downloads
TIMEOUT = 10     # Seconds to wait for a server response

def get_session():
    """
    Creates a requests Session with automatic retry logic.
    This helps handle temporary network failures or server blips.
    """
    session = requests.Session()
    retry = Retry(connect=3, backoff_factor=0.5)
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    session.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36"
    })
    return session

def clean_filename(url):
    """Generates a clean, safe filename from a URL."""
    fragment = url.split("/")[-1].split("?")[0]
    if not fragment.lower().endswith(".pdf"):
        fragment += ".pdf"
    # Remove characters that are illegal in filenames
    clean_name = "".join([c for c in fragment if c.isalpha() or c.isdigit() or c in (' ', '.', '_', '-')]).strip()
    return clean_name if clean_name else "document.pdf"

def download_file(args):
    """
    The worker function that runs in a thread.
    Args: (url, folder_path)
    """
    url, folder = args
    filename = clean_filename(url)
    save_path = os.path.join(folder, filename)
    
    # 1. Smart Resume: Check if file already exists
    if os.path.exists(save_path):
        return f"⏭️  Skipped (Already Exists): {filename}"

    session = get_session()

    try:
        # Stream=True allows us to check headers before downloading the whole body
        with session.get(url, stream=True, timeout=TIMEOUT) as response:
            response.raise_for_status()
            
            # 2. Validation: Ensure it's actually a PDF
            content_type = response.headers.get('Content-Type', '').lower()
            if 'application/pdf' not in content_type and 'application/octet-stream' not in content_type:
                return f"⚠️  Skipped (Not a PDF): {filename}"

            # 3. Write file to disk
            with open(save_path, 'wb') as f:
                for chunk in response.iter_content(chunk_size=8192):
                    f.write(chunk)
                    
        return None # Success

    except Exception as e:
        return f"❌ Error downloading {filename}: {str(e)}"

def main():
    print("--- 🚀 Advanced PDF Downloader (Threaded) ---")
    target_url = input("Enter target URL: ").strip()

    if not target_url.startswith("http"):
        print("Error: URL must start with http:// or https://")
        return

    # Create folder based on domain name
    domain = urlparse(target_url).netloc.replace("www.", "")
    folder_name = f"{domain}_downloads"
    if not os.path.exists(folder_name):
        os.makedirs(folder_name)

    print(f"\n🔍 Scanning {target_url}...")
    
    session = get_session()
    try:
        response = session.get(target_url)
        response.raise_for_status()
        soup = BeautifulSoup(response.content, "html.parser")
        
        # Find links
        links = []
        for a in soup.find_all('a', href=True):
            href = a['href']
            text = a.get_text().strip().upper()
            
            # Logic: Ends in .pdf OR Text says "PDF"
            if href.lower().endswith('.pdf') or "PDF" in text:
                full_url = urljoin(target_url, href)
                links.append(full_url)
        
        # Remove duplicates
        unique_links = list(set(links))
        
        if not unique_links:
            print("No PDF links found.")
            return
            
        print(f"✅ Found {len(unique_links)} unique PDF links.")
        print(f"📂 Saving to: ./{folder_name}/")
        print(f"⚡ Starting download with {MAX_THREADS} threads...")

        # Prepare arguments for the worker function
        download_args = [(link, folder_name) for link in unique_links]
        
        # --- MULTITHREADING START ---
        with ThreadPoolExecutor(max_workers=MAX_THREADS) as executor:
            # tqdm creates the visual progress bar
            # We map the download_file function to our list of links
            results = list(tqdm(executor.map(download_file, download_args), total=len(unique_links), unit="file"))
        # --- MULTITHREADING END ---

        # Print detailed report of skipped/failed files
        print("\n--- Download Report ---")
        errors = [r for r in results if r is not None]
        if errors:
            for err in errors:
                print(err)
        else:
            print("🎉 All files downloaded successfully!")

    except Exception as e:
        print(f"Critical Error: {e}")

if __name__ == "__main__":
    main()