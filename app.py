from collections import OrderedDict
from io import BytesIO
from pathlib import Path
import re
import uuid
import threading
import webbrowser
import zipfile

import pandas as pd
from flask import Flask, Response, abort, jsonify, render_template, request, send_file
from werkzeug.exceptions import RequestEntityTooLarge

from scraper_market_intelligence import (
    analyze_captions,
    build_report_bytes,
    clean_records_with_metrics,
    compare_segments,
    find_caption_column,
    find_segment_column,
    frame_to_records,
    limit_records_per_segment,
    make_experiments,
)
from tabular_analysis import analyze_table, read_uploaded_table


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_ANALYSES = 10
app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = MAX_UPLOAD_BYTES
REPORTS = OrderedDict()


def read_uploaded_records(upload):
    suffix = Path(upload.filename or "").suffix.lower()
    contents = BytesIO(upload.read())
    if suffix == ".csv":
        frame = pd.read_csv(contents)
        frames = [frame]
    elif suffix in {".xlsx", ".xls"}:
        frames = list(pd.read_excel(contents, sheet_name=None).values())
    else:
        raise ValueError("Format file harus CSV atau Excel (.csv, .xlsx, .xls).")

    frame = next((sheet for sheet in frames if find_caption_column(sheet)), None)
    if frame is None:
        raise ValueError(
            "Kolom caption tidak ditemukan. Gunakan Caption, Teks, Deskripsi, "
            "atau Sampel Caption."
        )

    segment_column = find_segment_column(frame)
    records, _ = frame_to_records(frame, segment_column)
    if segment_column is None:
        raise ValueError(
            "Kolom brand/kompetitor tidak ditemukan. Tambahkan kolom `brand` "
            "atau `competitor` agar data dapat dibandingkan per merek."
        )
    return records


def analyze_upload(upload, keyword, limit):
    if upload is None or not upload.filename:
        raise ValueError("Pilih file CSV atau Excel terlebih dahulu.")
    records = read_uploaded_records(upload)
    cleaned_records, quality = clean_records_with_metrics(records, keyword, "segment")
    cleaned_records = limit_records_per_segment(cleaned_records, limit)
    if not cleaned_records:
        raise ValueError(
            "Tidak ditemukan caption relevan. Periksa kata kunci atau file yang diunggah."
        )

    brands = sorted({
        str(record.get("segment", "")).strip()
        for record in cleaned_records
        if str(record.get("segment", "")).strip()
    })
    if len(brands) < 2:
        raise ValueError(
            "Setelah penyaringan, hanya ada satu merek/kompetitor. "
            "Pastikan file berisi minimal dua label kompetitor dengan caption relevan."
        )

    captions = [record["caption"] for record in cleaned_records]
    group_sizes = {
        brand: sum(record.get("segment") == brand for record in cleaned_records)
        for brand in brands
    }
    sample_rows, keyword_rows, theme_rows = analyze_captions(captions, keyword)
    for sample, record in zip(sample_rows, cleaned_records):
        sample["Merek / Kompetitor"] = record.get("segment", "")
    comparison_rows = compare_segments(cleaned_records)
    experiments = make_experiments(theme_rows, len(captions))

    report_bytes = build_report_bytes(
        keyword=keyword,
        source=f"File yang diunggah: {upload.filename}",
        requested_limit=limit,
        captions=captions,
        quality_metrics=quality,
        comparison_rows=comparison_rows,
        sample_rows=sample_rows,
    )
    report_id = uuid.uuid4().hex
    REPORTS[report_id] = report_bytes
    while len(REPORTS) > MAX_ANALYSES:
        REPORTS.popitem(last=False)

    return {
        "report_id": report_id,
        "keyword": keyword,
        "source": upload.filename,
        "brands": brands,
        "group_sizes": group_sizes,
        "sample_count": len(captions),
        "quality": quality,
        "themes": theme_rows,
        "comparison": comparison_rows,
        "keywords": keyword_rows,
        "samples": sample_rows,
        "experiments": experiments,
        "methodology": {
            "sampling": "Sampel observasional dari file unggahan; pemilihan sampel tidak diketahui.",
            "classification": "Pencocokan kamus kata kunci tetap; satu caption dapat memuat beberapa tema.",
            "comparison": "Selisih porsi adalah deskriptif dan menggunakan merek pertama secara alfabetis sebagai acuan.",
            "uncertainty": "Selang Wilson 95% mengasumsikan pengamatan binomial independen; tidak memperbaiki bias seleksi sampel.",
        },
        "notes": [
            "Persentase menghitung porsi caption dalam sampel tiap merek; bukan pangsa pasar atau preferensi seluruh pelanggan.",
            "Tema dideteksi dengan pencocokan kata kunci sederhana. Periksa sampel asli sebelum mengambil keputusan.",
            "Selang Wilson hanya ilustrasi ketidakpastian bila asumsi pengambilan sampel acak berlaku. Sampel convenience/non-acak tidak mendukung inferensi populasi.",
            "Gunakan data yang penggunaannya diizinkan dan hindari memasukkan informasi pribadi yang tidak diperlukan.",
        ],
    }


@app.get("/")
def index():
    portfolio = Path(__file__).resolve().with_name("index.html")
    return Response(portfolio.read_text(encoding="utf-8"), mimetype="text/html")


@app.get("/app")
def analysis_workbench():
    return render_template("index.html")


@app.get("/template.csv")
def download_template():
    template = BytesIO(b"caption,brand\n")
    template.seek(0)
    return send_file(
        template,
        mimetype="text/csv",
        as_attachment=True,
        download_name="template_riset_kompetitor.csv",
    )


@app.get("/contoh-data.csv")
def download_data_example():
    example = BytesIO(
        "tanggal,kategori,penjualan,jumlah\n"
        "2026-01-01,Kopi,125000,5\n"
        "2026-01-02,Teh,98000,4\n"
        "2026-01-03,Kopi,142000,6\n".encode("utf-8")
    )
    example.seek(0)
    return send_file(
        example,
        mimetype="text/csv",
        as_attachment=True,
        download_name="contoh_data_penjualan.csv",
    )


@app.post("/api/profile")
def profile_data():
    upload = request.files.get("file")
    if upload is None or not upload.filename:
        return jsonify({"error": "Pilih file data CSV atau Excel terlebih dahulu."}), 400
    try:
        frame, sheet_name, was_truncated = read_uploaded_table(upload)
        result = analyze_table(
            frame,
            source=upload.filename,
            sheet_name=sheet_name,
            was_truncated=was_truncated,
        )
    except (
        ValueError,
        OSError,
        pd.errors.ParserError,
        pd.errors.EmptyDataError,
        UnicodeDecodeError,
        zipfile.BadZipFile,
    ) as error:
        return jsonify({"error": str(error)}), 400

    report_id = uuid.uuid4().hex
    REPORTS[report_id] = result.pop("report_bytes")
    while len(REPORTS) > MAX_ANALYSES:
        REPORTS.popitem(last=False)
    result["report_id"] = report_id
    return jsonify(result)


@app.post("/api/analyze")
def analyze():
    keyword = request.form.get("keyword", "").strip()
    if not keyword:
        return jsonify({"error": "Masukkan topik atau kata kunci."}), 400
    if len(keyword) > 80:
        return jsonify({"error": "Kata kunci maksimal 80 karakter."}), 400

    try:
        limit = int(request.form.get("limit", "100"))
    except ValueError:
        return jsonify({"error": "Batas sampel harus berupa angka."}), 400
    if not 10 <= limit <= 10000:
        return jsonify({"error": "Batas sampel harus antara 10 hingga 10.000."}), 400

    upload = request.files.get("file")
    try:
        result = analyze_upload(upload, keyword, limit)
    except (ValueError, OSError, pd.errors.ParserError) as error:
        return jsonify({"error": str(error)}), 400
    return jsonify(result)


@app.get("/api/report/<report_id>")
def download_report(report_id):
    report = REPORTS.get(report_id)
    if report is None:
        abort(404, description="Laporan tidak ditemukan. Jalankan ulang analisis.")
    keyword = request.args.get("keyword", "market_research")
    safe_keyword = re.sub(r"[^\w-]+", "_", keyword, flags=re.UNICODE).strip("_")
    report_file = BytesIO(report)
    report_file.seek(0)
    return send_file(
        report_file,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=f"laporan_riset_{safe_keyword or 'pasar'}.xlsx",
    )


@app.errorhandler(RequestEntityTooLarge)
def upload_too_large(_error):
    return jsonify({"error": "Ukuran file maksimal 10 MB."}), 413


@app.errorhandler(404)
def not_found(error):
    if request.path.startswith("/api/"):
        return jsonify({"error": error.description}), 404
    return error


if __name__ == "__main__":
    threading.Timer(1.0, lambda: webbrowser.open("http://127.0.0.1:5000")).start()
    app.run(host="127.0.0.1", port=5000, debug=False)
