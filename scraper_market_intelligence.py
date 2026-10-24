import argparse
from collections import Counter
from datetime import datetime
from io import BytesIO
from pathlib import Path
import re
from urllib.parse import quote_plus

import pandas as pd


MAX_CAPTION_LENGTH = 500
STOP_WORDS = {
    "yang", "untuk", "dengan", "dan", "dari", "ini", "itu", "ada", "bisa",
    "juga", "kalo", "kalau", "buat", "banget", "sangat", "aja", "saja",
    "sih", "nih", "nya", "the", "and", "for", "with", "this", "that",
}
BLACKLIST_PHRASES = (
    "liked", "followed", "commented", "reposted", "replied", "notification",
    "messages", "inbox", "activity", "mentions", "followers", "secure your account",
    "started following",
)
CAPTION_COLUMN_NAMES = {
    "caption",
    "teks",
    "deskripsi",
    "judul / caption konten produk",
    "sampel caption",
    "sampel caption / teks pasar",
}
SEGMENT_COLUMN_NAMES = {
    "brand",
    "merek",
    "kompetitor",
    "competitor",
    "akun",
    "account",
    "nama toko",
    "seller",
    "sumber",
}
FEATURES = {
    "Harga dan promo": {"murah", "harga", "diskon", "promo", "voucher", "cashback", "sale"},
    "Fungsi dan penggunaan": {
        "fungsi", "perekat", "merekatkan", "bungkus", "packing", "kabel",
        "paket", "serbaguna", "menutup", "rekat",
    },
    "Kualitas dan daya tahan": {"kuat", "awet", "tahan", "kualitas", "premium", "tebal"},
    "Material dan warna": {"bahan", "bening", "coklat", "plastik", "kertas", "kain", "kulit", "kanvas"},
    "Ukuran dan kuantitas": {"ukuran", "panjang", "lebar", "pcs", "roll", "meter", "isi"},
    "Gaya dan desain": {"minimalis", "aesthetic", "estetik", "elegan", "korea", "model", "desain", "warna"},
}
CONTENT_ANGLES = {
    "Promo dan harga": {"diskon", "promo", "voucher", "cashback", "sale", "murah"},
    "Edukasi dan rekomendasi": {"tips", "rekomendasi", "cara", "pilih", "perbandingan", "review"},
    "Demo penggunaan": {"tutorial", "cara", "dipakai", "digunakan", "contoh", "hasil"},
}


def normalize_caption(value):
    if not isinstance(value, str):
        return ""
    return re.sub(r"\s+", " ", value).strip()


def tokenize(text):
    return re.findall(r"(?u)\b[\w-]+\b", text.lower())


def clean_captions(captions, keyword):
    cleaned, _ = clean_captions_with_metrics(captions, keyword)
    return cleaned


def clean_captions_with_metrics(captions, keyword):
    records = [{"caption": caption} for caption in captions]
    cleaned_records, metrics = clean_records_with_metrics(records, keyword)
    return [record["caption"] for record in cleaned_records], metrics


def clean_records_with_metrics(records, keyword, segment_field=None):
    query_terms = set(tokenize(keyword))
    cleaned = []
    seen = set()
    metrics = {
        "Kandidat dari sumber": 0,
        "Teks layak setelah filter dasar": 0,
        "Baris tanpa label kompetitor": 0,
        "Relevan dengan kata kunci": 0,
        "Duplikat yang dihapus": 0,
    }

    for record in records:
        metrics["Kandidat dari sumber"] += 1
        caption = normalize_caption(record.get("caption"))
        lowered = caption.lower()
        if not 30 <= len(caption) <= MAX_CAPTION_LENGTH:
            continue
        if any(phrase in lowered for phrase in BLACKLIST_PHRASES):
            continue
        metrics["Teks layak setelah filter dasar"] += 1

        segment = normalize_caption(record.get(segment_field)) if segment_field else ""
        if segment_field and not segment:
            metrics["Baris tanpa label kompetitor"] += 1
            continue
        caption_tokens = tokenize(caption)
        is_relevant = not query_terms or any(
            token == query_term or token.startswith(query_term)
            for token in caption_tokens
            for query_term in query_terms
        )
        if not is_relevant:
            continue
        metrics["Relevan dengan kata kunci"] += 1

        dedupe_key = (segment.lower(), lowered)
        if dedupe_key in seen:
            metrics["Duplikat yang dihapus"] += 1
            continue
        cleaned.append({**record, "caption": caption})
        seen.add(dedupe_key)

    return cleaned, metrics


def limit_records_per_segment(records, limit, segment_field="segment"):
    grouped = {}
    for record in records:
        segment = normalize_caption(record.get(segment_field))
        grouped.setdefault(segment, []).append(record)

    selected = []
    segments = list(grouped)
    while len(selected) < limit:
        added_record = False
        for segment in segments:
            if grouped[segment] and len(selected) < limit:
                selected.append(grouped[segment].pop(0))
                added_record = True
        if not added_record:
            break
    return selected


def matching_terms(tokens, vocabulary):
    return sorted(set(tokens).intersection(vocabulary))


def analyze_captions(captions, keyword=""):
    query_terms = set(tokenize(keyword))
    tokenized_captions = [tokenize(caption) for caption in captions]
    term_counts = Counter()
    for tokens in tokenized_captions:
        terms_in_caption = {
            token for token in tokens
            if len(token) >= 4 and token not in STOP_WORDS
            and not any(token == term or token.startswith(term) for term in query_terms)
        }
        term_counts.update(terms_in_caption)

    feature_counts = Counter()
    structured_rows = []
    for caption, tokens in zip(captions, tokenized_captions):
        themes = [
            theme for theme, vocabulary in FEATURES.items()
            if matching_terms(tokens, vocabulary)
        ]
        angle_matches = [
            angle for angle, vocabulary in CONTENT_ANGLES.items()
            if matching_terms(tokens, vocabulary)
        ]
        structured_rows.append({
            "Sampel Caption": caption,
            "Tema yang Terdeteksi": ", ".join(themes) if themes else "Belum terklasifikasi",
            "Angle Konten (heuristik)": ", ".join(angle_matches) if angle_matches else "Belum terklasifikasi",
        })
        feature_counts.update(themes)

    keyword_rows = [
        {"Kata Kunci": term, "Jumlah Caption yang Menyebut": count}
        for term, count in term_counts.most_common(15)
    ]
    feature_rows = [
        {"Tema": theme, "Jumlah Caption": count}
        for theme, count in feature_counts.most_common()
    ]
    return structured_rows, keyword_rows, feature_rows


def compare_segments(records, segment_field="segment"):
    grouped_captions = {}
    for record in records:
        segment = normalize_caption(record.get(segment_field))
        if segment:
            grouped_captions.setdefault(segment, []).append(record["caption"])

    if len(grouped_captions) < 2:
        return []

    rows = []
    reference_segment = next(iter(sorted(grouped_captions)))
    reference_captions = grouped_captions[reference_segment]
    reference_features = analyze_captions(reference_captions)[2]
    reference_counts = {
        row["Tema"]: row["Jumlah Caption"] for row in reference_features
    }
    for segment, captions in sorted(grouped_captions.items()):
        _, _, feature_rows = analyze_captions(captions)
        theme_counts = {row["Tema"]: row["Jumlah Caption"] for row in feature_rows}
        for theme in FEATURES:
            count = theme_counts.get(theme, 0)
            proportion = count / len(captions)
            lower, upper = wilson_interval(count, len(captions))
            reference_proportion = (
                reference_counts.get(theme, 0) / len(reference_captions)
            )
            rows.append({
                "Kompetitor / Segmen": segment,
                "Jumlah Caption": len(captions),
                "Tema": theme,
                "Caption dengan Tema": count,
                "Porsi Caption (%)": round(proportion * 100, 1),
                "Selang Wilson 95% bawah (%)": round(lower * 100, 1),
                "Selang Wilson 95% atas (%)": round(upper * 100, 1),
                f"Selisih vs {reference_segment} (pp)": round(
                    (proportion - reference_proportion) * 100, 1
                ),
            })
    return rows


def wilson_interval(successes, sample_size, z_score=1.96):
    if sample_size <= 0:
        return 0.0, 0.0
    proportion = successes / sample_size
    z_squared = z_score ** 2
    denominator = 1 + z_squared / sample_size
    center = (proportion + z_squared / (2 * sample_size)) / denominator
    margin = (
        z_score
        * (
            proportion * (1 - proportion) / sample_size
            + z_squared / (4 * sample_size ** 2)
        ) ** 0.5
        / denominator
    )
    return max(0.0, center - margin), min(1.0, center + margin)


def make_experiments(feature_rows, sample_count):
    if sample_count < 10:
        return [{
            "Prioritas": "Kumpulkan data tambahan",
            "Dasar temuan": f"Hanya ada {sample_count} caption relevan dan unik; terlalu sedikit untuk membandingkan tema.",
            "Eksperimen yang disarankan": "Tambah sampel dari sumber dan periode yang jelas, lalu periksa ulang tema sebelum menyusun uji konten.",
            "Metrik untuk diuji": "Kelengkapan sampel dan konsistensi klasifikasi",
            "Status": "Belum cukup bukti untuk rekomendasi konten",
        }]

    observed_themes = [row for row in feature_rows if row["Jumlah Caption"] > 0]
    if len(observed_themes) < 2:
        return [{
            "Prioritas": "Validasi kebutuhan data",
            "Dasar temuan": "Sampel belum menunjukkan sedikitnya dua tema produk yang bisa dibandingkan.",
            "Eksperimen yang disarankan": "Tinjau ulang kata kunci, sumber, dan kamus klasifikasi; kumpulkan sampel yang lebih relevan sebelum memilih angle.",
            "Metrik untuk diuji": "Proporsi caption relevan dan cakupan tema",
            "Status": "Belum cukup bukti untuk membandingkan angle",
        }]

    first, second = observed_themes[:2]
    return [{
        "Prioritas": "Uji dua angle konten",
        "Dasar temuan": (
            f"Tema “{first['Tema']}” ditemukan pada {first['Jumlah Caption']} caption; "
            f"tema “{second['Tema']}” pada {second['Jumlah Caption']} caption "
            f"dari {sample_count} caption unik."
        ),
        "Eksperimen yang disarankan": (
            f"Bandingkan konten yang menonjolkan “{first['Tema']}” dengan konten "
            f"“{second['Tema']}” pada audiens dan periode sebanding."
        ),
        "Metrik untuk diuji": "CTR atau engagement; konversi bila tersedia, dengan biaya dan periode yang sama",
        "Status": "Hipotesis untuk diuji; bukan bukti dampak bisnis",
    }]


def collect_from_tiktok(keyword, limit):
    try:
        from playwright.sync_api import Error as PlaywrightError
        from playwright.sync_api import sync_playwright
    except ModuleNotFoundError as error:
        raise RuntimeError(
            "Pengambilan browser memerlukan Playwright. Untuk aplikasi riset "
            "kompetitor, unggah file CSV atau Excel."
        ) from error

    url = f"https://www.tiktok.com/search?q={quote_plus(keyword)}"
    captions = []
    blacklist = BLACKLIST_PHRASES

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=False)
        page = browser.new_page(viewport={"width": 1280, "height": 800})
        try:
            page.goto(url, wait_until="domcontentloaded", timeout=60000)
            page.wait_for_timeout(8000)
            for _ in range(4):
                page.evaluate("window.scrollBy(0, 900)")
                page.wait_for_timeout(2000)

            elements = page.locator("div[data-e2e], h3").all()
            for element in elements:
                text = normalize_caption(element.inner_text(timeout=3000))
                lowered = text.lower()
                if not 30 <= len(text) <= MAX_CAPTION_LENGTH or "\n" in text:
                    continue
                if any(phrase in lowered for phrase in blacklist):
                    continue
                captions.append(text)
                if len(captions) >= limit * 3:
                    break
        except PlaywrightError as error:
            raise RuntimeError(
                f"Gagal mengambil hasil dari halaman pencarian. "
                f"Periksa koneksi, akses, dan aturan sumber data. Detail: {error}"
            ) from error
        finally:
            browser.close()

    return captions, url


def load_input_file(input_path):
    path = Path(input_path)
    if not path.is_file():
        raise FileNotFoundError(f"File input tidak ditemukan: {path}")
    if path.suffix.lower() == ".csv":
        frame = pd.read_csv(path)
        return extract_captions(frame), f"File yang disediakan: {path.name}"
    elif path.suffix.lower() in {".xlsx", ".xls"}:
        sheets = pd.read_excel(path, sheet_name=None)
    else:
        raise ValueError("Format input harus CSV atau Excel (.csv, .xlsx, .xls).")

    captions, sheet_name = extract_captions_from_sheets(sheets)
    return captions, f"File yang disediakan: {path.name} · sheet {sheet_name}"


def extract_captions_from_sheets(sheets):
    for sheet_name, frame in sheets.items():
        try:
            captions = extract_captions(frame)
        except ValueError:
            continue
        return captions, sheet_name
    raise ValueError("Tidak ada sheet Excel dengan kolom caption yang dikenali.")


def extract_captions(frame):
    caption_column = find_caption_column(frame)
    if caption_column is None:
        raise ValueError(
            "Kolom caption tidak ditemukan. Gunakan nama kolom Caption, Teks, "
            "Deskripsi, Sampel Caption, atau Sampel Caption / Teks Pasar."
        )
    return frame[caption_column].tolist()


def find_caption_column(frame):
    return next(
        (
            column for column in frame.columns
            if str(column).strip().lower() in CAPTION_COLUMN_NAMES
        ),
        None,
    )


def find_segment_column(frame):
    return next(
        (
            column for column in frame.columns
            if str(column).strip().lower() in SEGMENT_COLUMN_NAMES
        ),
        None,
    )


def frame_to_records(frame, segment_column=None):
    caption_column = find_caption_column(frame)
    if caption_column is None:
        raise ValueError(
            "Kolom caption tidak ditemukan. Gunakan Caption, Teks, Deskripsi, "
            "atau Sampel Caption."
        )
    records = []
    for _, row in frame.iterrows():
        record = {"caption": row[caption_column]}
        if segment_column:
            record["segment"] = row[segment_column]
        records.append(record)
    return records, caption_column


def build_report_bytes(
    keyword,
    source,
    requested_limit,
    captions,
    quality_metrics,
    comparison_rows=None,
    sample_rows=None,
):
    analyzed_samples, keyword_rows, feature_rows = analyze_captions(captions, keyword)
    if sample_rows is None:
        sample_rows = analyzed_samples
    experiments = make_experiments(feature_rows, len(captions))
    captured_at = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M:%S %Z")

    summary_rows = [
        {"Indikator": "Topik pencarian", "Nilai": keyword},
        {"Indikator": "Sumber", "Nilai": source},
        {"Indikator": "Waktu pengambilan", "Nilai": captured_at},
        {"Indikator": "Target maksimum sampel", "Nilai": requested_limit},
        *[
            {"Indikator": label, "Nilai": value}
            for label, value in quality_metrics.items()
        ],
        {"Indikator": "Caption relevan dan unik", "Nilai": len(captions)},
        {"Indikator": "Metode sampling", "Nilai": "Sampel observasional dari file yang diunggah; representativitas tidak diketahui."},
        {"Indikator": "Protokol deduplikasi", "Nilai": "Teks caption identik dihapus dalam kelompok merek yang sama."},
        {"Indikator": "Cara baca", "Nilai": "Jumlah menunjukkan berapa caption unik yang menyebut tema/kata, bukan jumlah orang atau ukuran permintaan."},
        {"Indikator": "Metode klasifikasi", "Nilai": "Pencocokan kata kunci sederhana; tinjau sampel asli sebelum mengambil keputusan."},
        {"Indikator": "Selang Wilson", "Nilai": "Rentang deskriptif berbasis asumsi binomial. Sampel non-acak tidak mendukung inferensi populasi."},
    ]

    report = BytesIO()
    with pd.ExcelWriter(report, engine="openpyxl") as writer:
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name="Ringkasan Keputusan", index=False)
        pd.DataFrame(sample_rows).to_excel(writer, sheet_name="Sampel Terklasifikasi", index=False)
        pd.DataFrame(keyword_rows).to_excel(writer, sheet_name="Kata Kunci", index=False)
        pd.DataFrame(feature_rows).to_excel(writer, sheet_name="Tema Produk", index=False)
        pd.DataFrame(experiments).to_excel(writer, sheet_name="Eksperimen Berikutnya", index=False)
        if comparison_rows:
            pd.DataFrame(comparison_rows).to_excel(
                writer, sheet_name="Perbandingan Kompetitor", index=False
            )

    return report.getvalue()


def write_report(keyword, source, requested_limit, captions, quality_metrics, output_path):
    output_path = Path(output_path)
    output_path.write_bytes(
        build_report_bytes(keyword, source, requested_limit, captions, quality_metrics)
    )
    return output_path


def parse_args():
    parser = argparse.ArgumentParser(
        description="Kumpulkan dan analisis sampel konten publik secara transparan."
    )
    parser.add_argument("--keyword", default="lakban", help="Topik produk yang dianalisis.")
    parser.add_argument("--limit", type=int, default=50, help="Maksimum caption unik yang dianalisis.")
    parser.add_argument("--input", help="CSV/Excel berisi data yang Anda berwenang gunakan; melewati pengambilan browser.")
    parser.add_argument("--output", help="Path file Excel hasil.")
    args = parser.parse_args()
    if not args.keyword.strip():
        parser.error("--keyword tidak boleh kosong.")
    if args.limit < 1:
        parser.error("--limit minimal 1.")
    return args


def run_market_intelligence():
    args = parse_args()
    safe_keyword = re.sub(r"[^\w-]+", "_", args.keyword.strip(), flags=re.UNICODE).strip("_")
    output_path = args.output or f"laporan_analisis_pasar_{safe_keyword}.xlsx"

    if args.input:
        raw_captions, source = load_input_file(args.input)
    else:
        print(
            "Mengambil teks yang terlihat pada halaman pencarian. "
            "Lanjutkan hanya bila cara akses ini diizinkan oleh sumber data."
        )
        raw_captions, source = collect_from_tiktok(args.keyword.strip(), args.limit)

    captions, quality_metrics = clean_captions_with_metrics(
        raw_captions, args.keyword.strip()
    )
    captions = captions[:args.limit]
    if not captions:
        raise RuntimeError(
            "Tidak ditemukan caption unik yang relevan. Laporan tidak dibuat agar "
            "data kosong tidak disamarkan sebagai insight."
        )

    report_path = write_report(
        args.keyword.strip(), source, args.limit, captions, quality_metrics, output_path
    )
    print(f"Sampel relevan dan unik: {len(captions)}")
    print(f"Laporan keputusan tersimpan: {report_path.resolve()}")
    if len(captions) < 10:
        print("Catatan: jumlah sampel kecil; laporan tidak menyarankan uji angle konten.")


if __name__ == "__main__":
    run_market_intelligence()
