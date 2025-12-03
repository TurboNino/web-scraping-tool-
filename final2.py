import os
import sys
import time
import csv
import requests
from bs4 import BeautifulSoup
from pathvalidate import sanitize_filename
from urllib.parse import urljoin

from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import inch

DOCTOR_SECTIONS = {
    "first_doctor":  "https://classicdoctorwhocomics.wordpress.com/first-doctor-comics/",
    "second_doctor": "https://classicdoctorwhocomics.wordpress.com/second-doctor-comics/",
    "third_doctor":  "https://classicdoctorwhocomics.wordpress.com/third-doctor-comics/",
    "fourth_doctor": "https://classicdoctorwhocomics.wordpress.com/fourth-doctor-comics/",
}

def make_safe_name(name: str) -> str:
    name = name.strip()
    name = sanitize_filename(name)
    name = name.replace(" ", "_")
    name = name.lower()
    return name

def get_project_root() -> str:
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def get_download_root() -> str:
    desktop = os.path.join(os.path.expanduser("~"), "Desktop")
    download_root = os.path.join(desktop, "comic_images")
    os.makedirs(download_root, exist_ok=True)
    print("\nDownload folder:", download_root)
    return download_root


def setup_doctor_folder(download_root: str, doctor_key: str) -> str:
    doctor_folder = os.path.join(download_root, doctor_key)
    os.makedirs(doctor_folder, exist_ok=True)
    return doctor_folder

def download_image(img_url: str, filepath: str):
    try:
        resp = requests.get(img_url, timeout=20)
        resp.raise_for_status()
        with open(filepath, "wb") as f:
            f.write(resp.content)
        print("  -> saved:", filepath)
    except Exception as e:
        print("  !! ERROR downloading", img_url, ":", e)

def scrape_doctor_section(section_url: str, doctor_key: str, download_root: str):
    doctor_folder = setup_doctor_folder(download_root, doctor_key)
    print(f"\n=== Doctor: {doctor_key} ===")
    print("Section URL:", section_url)
    print("Doctor folder:", doctor_folder)
    resp = requests.get(section_url, timeout=20)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    current_title = None
    image_counters = {}
    titles_for_doctor = []
    titles_seen = set()
    for node in soup.find_all(["h2", "img"]):
        if node.name == "h2":
            raw_title = node.get_text()
            title_text = (raw_title or "").strip()
            print("\n[RAW TITLE]:", repr(title_text))
            if not title_text:
                print("  -> empty title after strip, ignored.")
                current_title = None
                continue
            safe_title = make_safe_name(title_text)
            if not safe_title:
                print("  -> title discarded (empty after sanitize), no folder.")
                current_title = None
                continue
            current_title = title_text
            title_folder = os.path.join(doctor_folder, safe_title)
            os.makedirs(title_folder, exist_ok=True)
            image_counters[current_title] = 0
            print("  [VALID TITLE]:", current_title)
            print("  folder:", title_folder)
            if safe_title not in titles_seen:
                titles_seen.add(safe_title)
                titles_for_doctor.append((doctor_key, title_text.lower(), safe_title))
            continue
        if node.name == "img":
            if current_title is None:
                continue
            src = node.get("src")
            if not src:
                continue
            img_url = urljoin(section_url, src)
            image_counters[current_title] += 1
            page_num = image_counters[current_title]
            safe_title = make_safe_name(current_title)
            title_folder = os.path.join(doctor_folder, safe_title)
            filename = f"page_{page_num:02d}.jpg"
            filepath = os.path.join(title_folder, filename)
            print(" image for:", current_title)
            download_image(img_url, filepath)
            time.sleep(0.3)
    return titles_for_doctor

def create_csv(all_rows: list, csv_path: str):
    with open(csv_path, "w", encoding="utf-8", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["index", "doctor", "title_lower", "title_safe"])
        counter = 0
        for doctor_key, title_lower, title_safe in all_rows:
            counter += 1
            writer.writerow([counter, doctor_key, title_lower, title_safe])
    print("\nCSV created:", csv_path)

def create_pdf(all_rows: list, pdf_path: str):
    doc = SimpleDocTemplate(pdf_path, pagesize=letter)
    story = []
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        textColor=colors.black,
        spaceAfter=20,
    )
    story.append(Paragraph("Classic Doctor Who Comics - Title List", title_style))
    story.append(Spacer(1, 0.3 * inch))
    data = [["#", "Doctor", "Title (lower)", "Title (safe)"]]
    counter = 0
    for doctor_key, title_lower, title_safe in all_rows:
        counter += 1
        data.append([str(counter), doctor_key, title_lower, title_safe])
    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.grey),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
        ('ALIGN', (0, 0), (-1, -1), 'LEFT'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, 0), 11),
        ('BOTTOMPADDING', (0, 0), (-1, 0), 8),
        ('FONTNAME', (0, 1), (-1, -1), 'Helvetica'),
        ('FONTSIZE', (0, 1), (-1, -1), 9),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.lightgrey]),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
    ]))
    story.append(table)
    doc.build(story)
    print("PDF created:", pdf_path)

def choose_doctor_keys():
    options = list(DOCTOR_SECTIONS.keys())
    print("\nSelect which Doctor to process:")
    for idx, key in enumerate(options, start=1):
        print(f"{idx}. {key}")
    print(f"{len(options)+1}. all")
    choice = input("> ").strip()
    try:
        num = int(choice)
    except ValueError:
        print("Invalid choice, exiting.")
        return []
    if num == len(options) + 1:
        return options
    if 1 <= num <= len(options):
        return [options[num-1]]
    print("Invalid choice, exiting.")
    return []

def main():
    print("=== Classic Doctor Who Comics Downloader (Images + CSV + PDF) ===")
    download_root = get_download_root()
    doctor_keys = choose_doctor_keys()
    if not doctor_keys:
        return
    all_rows = []
    for key in doctor_keys:
        url = DOCTOR_SECTIONS.get(key)
        if not url:
            print("No URL configured for", key)
            continue
        titles_for_doctor = scrape_doctor_section(url, key, download_root)
        all_rows.extend(titles_for_doctor)
    csv_path = os.path.join(download_root, "titles_list.csv")
    pdf_path = os.path.join(download_root, "titles_list.pdf")
    if all_rows:
        create_csv(all_rows, csv_path)
        create_pdf(all_rows, pdf_path)
    else:
        print("\nNo valid titles found, CSV/PDF not created.")
    print("\nDONE. Everything saved in:", download_root)

if __name__ == "__main__":
    main()