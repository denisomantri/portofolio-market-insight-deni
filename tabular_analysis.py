from io import BytesIO
from pathlib import Path

import pandas as pd
from pandas.api.types import is_datetime64_any_dtype, is_numeric_dtype


MAX_PROFILE_ROWS = 50_000
MAX_PROFILE_COLUMNS = 60


def read_uploaded_table(upload):
    suffix = Path(upload.filename or "").suffix.lower()
    contents = BytesIO(upload.read())
    if suffix == ".csv":
        try:
            frame = pd.read_csv(contents, nrows=MAX_PROFILE_ROWS + 1)
        except UnicodeDecodeError as error:
            raise ValueError(
                "CSV tidak terbaca. Simpan ulang file sebagai CSV UTF-8 lalu coba lagi."
            ) from error
        except pd.errors.EmptyDataError as error:
            raise ValueError("CSV kosong atau tidak memiliki judul kolom.") from error
        sheet_name = "CSV"
    elif suffix in {".xlsx", ".xls"}:
        with pd.ExcelFile(contents) as workbook:
            sheet_name = None
            frame = None
            for name in workbook.sheet_names:
                sheet = pd.read_excel(
                    workbook,
                    sheet_name=name,
                    nrows=MAX_PROFILE_ROWS + 1,
                )
                if not sheet.empty and len(sheet.columns):
                    sheet_name, frame = name, sheet
                    break
        if frame is None:
            raise ValueError("File tidak memiliki sheet berisi data.")
        frame = frame.head(MAX_PROFILE_ROWS + 1)
    else:
        raise ValueError("Format file harus CSV atau Excel (.csv, .xlsx, .xls).")

    if frame.empty or not len(frame.columns):
        raise ValueError("File tidak berisi baris data.")

    was_truncated = len(frame) > MAX_PROFILE_ROWS
    frame = frame.head(MAX_PROFILE_ROWS).copy()
    if len(frame.columns) > MAX_PROFILE_COLUMNS:
        raise ValueError(
            f"File memiliki {len(frame.columns)} kolom. Batas yang didukung "
            f"adalah {MAX_PROFILE_COLUMNS} kolom."
        )
    names = []
    used_names = set()
    for index, column in enumerate(frame.columns):
        name = str(column).strip() or f"Kolom {index + 1}"
        candidate = name
        suffix_number = 2
        while candidate in used_names:
            candidate = f"{name}_{suffix_number}"
            suffix_number += 1
        names.append(candidate)
        used_names.add(candidate)
    frame.columns = names
    frame = frame.replace(r"^\s*$", pd.NA, regex=True)
    return frame, sheet_name, was_truncated


def _format_value(value):
    if pd.isna(value):
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    if hasattr(value, "item"):
        value = value.item()
    if isinstance(value, (str, int, float, bool)):
        return value
    return str(value)


def _is_date_column(series, column_name):
    if is_datetime64_any_dtype(series):
        return True
    name_suggests_date = any(
        term in str(column_name).lower()
        for term in ("date", "tanggal", "time", "waktu", "bulan", "tahun")
    )
    if not name_suggests_date:
        return False
    values = series.dropna()
    if values.empty:
        return False
    parsed = pd.to_datetime(values, errors="coerce")
    return parsed.notna().mean() >= 0.8


def _profile_column(frame, column_name):
    series = frame[column_name]
    populated = series.dropna()
    missing_count = int(series.isna().sum())
    unique_count = int(populated.nunique())
    profile = {
        "column": str(column_name),
        "missing": missing_count,
        "missing_percent": round(missing_count / max(len(series), 1) * 100, 1),
        "unique": unique_count,
        "unparsed": 0,
    }

    if _is_date_column(series, column_name):
        values = pd.to_datetime(populated, errors="coerce").dropna()
        profile.update({
            "type": "Tanggal",
            "unparsed": int(len(populated) - len(values)),
            "minimum": _format_value(values.min()) if not values.empty else None,
            "maximum": _format_value(values.max()) if not values.empty else None,
            "description": "Rentang waktu yang tercatat",
        })
        return profile

    numeric = pd.to_numeric(populated, errors="coerce")
    if is_numeric_dtype(series) or (
        not populated.empty and numeric.notna().mean() >= 0.8
    ):
        values = numeric.dropna()
        profile.update({
            "type": "Angka",
            "unparsed": 0 if is_numeric_dtype(series) else int(len(populated) - len(values)),
            "minimum": _format_value(values.min()) if not values.empty else None,
            "maximum": _format_value(values.max()) if not values.empty else None,
            "mean": round(float(values.mean()), 3) if not values.empty else None,
            "median": round(float(values.median()), 3) if not values.empty else None,
            "description": "Nilai terkecil, terbesar, rata-rata, dan median",
        })
        return profile

    text_values = populated.astype(str)
    if not text_values.empty and (
        unique_count / len(text_values) > 0.6
        and text_values.str.len().mean() > 40
    ):
        profile.update({
            "type": "Teks",
            "average_length": round(float(text_values.str.len().mean()), 1),
            "examples": text_values.head(3).tolist(),
            "description": "Panjang rata-rata teks dan beberapa contoh",
        })
        return profile

    counts = text_values.value_counts().head(5)
    profile.update({
        "type": "Kategori",
        "top_values": [
            {"value": str(value), "count": int(count)}
            for value, count in counts.items()
        ],
        "description": "Kategori yang paling sering muncul",
    })
    return profile


def analyze_table(frame, source, sheet_name, was_truncated):
    profiles = [_profile_column(frame, column) for column in frame.columns]
    missing_cells = int(frame.isna().sum().sum())
    total_cells = int(frame.shape[0] * frame.shape[1])
    findings = [
        f"File berisi {len(frame):,} baris dan {len(frame.columns)} kolom."
    ]
    if missing_cells:
        findings.append(
            f"Ada {missing_cells:,} sel kosong "
            f"({missing_cells / max(total_cells, 1) * 100:.1f}% dari seluruh sel)."
        )
    else:
        findings.append("Tidak ditemukan sel kosong pada data yang dibaca.")
    incomplete = [
        profile for profile in profiles
        if profile["missing_percent"] >= 20
    ]
    if incomplete:
        most_incomplete = max(incomplete, key=lambda item: item["missing_percent"])
        findings.append(
            f"Kolom “{most_incomplete['column']}” memiliki "
            f"{most_incomplete['missing_percent']:.1f}% data kosong; periksa "
            "dampaknya sebelum memakai kolom ini."
        )
    if was_truncated:
        findings.append(
            f"Analisis dibatasi ke {MAX_PROFILE_ROWS:,} baris pertama."
        )

    preview = [
        {
            str(column): _format_value(value)
            for column, value in row.items()
        }
        for row in frame.head(20).to_dict(orient="records")
    ]
    summary_rows = [
        {"Indikator": "File", "Nilai": source},
        {"Indikator": "Sheet dianalisis", "Nilai": sheet_name},
        {"Indikator": "Jumlah baris dianalisis", "Nilai": len(frame)},
        {"Indikator": "Jumlah kolom", "Nilai": len(frame.columns)},
        {"Indikator": "Sel kosong", "Nilai": missing_cells},
        {"Indikator": "Persentase sel kosong", "Nilai": round(missing_cells / max(total_cells, 1) * 100, 1)},
        {"Indikator": "Batas baris diterapkan", "Nilai": was_truncated},
    ]

    report = BytesIO()
    with pd.ExcelWriter(report, engine="openpyxl") as writer:
        pd.DataFrame(summary_rows).to_excel(writer, sheet_name="Ringkasan", index=False)
        pd.DataFrame(profiles).to_excel(writer, sheet_name="Profil Kolom", index=False)
        frame.head(20).to_excel(writer, sheet_name="Contoh Data", index=False)

    return {
        "source": source,
        "sheet": sheet_name,
        "row_count": len(frame),
        "column_count": len(frame.columns),
        "missing_count": missing_cells,
        "missing_percent": round(missing_cells / max(total_cells, 1) * 100, 1),
        "truncated": was_truncated,
        "profiles": profiles,
        "findings": findings,
        "preview": preview,
        "report_bytes": report.getvalue(),
    }
