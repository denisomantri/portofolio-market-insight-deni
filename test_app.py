from io import BytesIO
import unittest

import pandas as pd

from app import app


class MarketInsightAppTests(unittest.TestCase):
    def setUp(self):
        app.config["TESTING"] = True
        self.client = app.test_client()

    def test_homepage_loads_integrated_portfolio(self):
        response = self.client.get("/")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Deni Somantri", response.data)
        self.assertIn(b"Portofolio analisis data", response.data)
        self.assertIn(b'href="/app"', response.data)
        self.assertIn(b"aplikasi analisis", response.data.lower())
        self.assertIn(b"demo-tab-profile", response.data)
        self.assertIn(b"Data Analyst", response.data)
        self.assertIn(b"bukan proyek klien", response.data)
        self.assertNotIn(b"streamlit", response.data.lower())

    def test_analysis_workbench_is_accessible_from_portfolio(self):
        response = self.client.get("/app")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Market Insight", response.data)
        self.assertIn(b"Analisis data umum", response.data)
        self.assertIn(b"survei", response.data)
        self.assertIn(b"caption,brand", response.data)
        self.assertIn(b"Cara membaca hasil dan batasannya", response.data)
        self.assertIn(b"Kembali ke portofolio", response.data)
        self.assertIn(b"method-grid", response.data)

    def test_competitor_template_is_downloadable(self):
        response = self.client.get("/template.csv")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"caption,brand", response.data)
        self.assertIn("attachment", response.headers["Content-Disposition"])

    def test_example_table_data_is_downloadable(self):
        response = self.client.get("/contoh-data.csv")

        self.assertEqual(response.status_code, 200)
        self.assertIn(b"tanggal,kategori,penjualan,jumlah", response.data)
        self.assertIn("attachment", response.headers["Content-Disposition"])

    def test_general_profile_analyzes_multiple_column_types_and_exports_report(self):
        frame = pd.DataFrame({
            "tanggal": ["2026-01-01", "2026-01-02", "2026-01-03"],
            "penjualan": [125000, 98000, 142000],
            "kategori": ["Kopi", "Teh", "Kopi"],
            "catatan": [
                "Pelanggan membeli kopi untuk acara kantor pada hari pertama",
                "Pelanggan membeli teh untuk konsumsi rumah tangga hari ini",
                "Pelanggan membeli kopi dan beberapa produk tambahan lainnya",
            ],
            "opsional": [None, "ada", None],
        })
        csv_file = BytesIO(frame.to_csv(index=False).encode("utf-8"))
        response = self.client.post(
            "/api/profile",
            data={"file": (csv_file, "data-penjualan.csv")},
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["row_count"], 3)
        self.assertEqual(data["column_count"], 5)
        self.assertEqual(data["missing_count"], 2)
        profiles = {profile["column"]: profile for profile in data["profiles"]}
        self.assertEqual(profiles["tanggal"]["type"], "Tanggal")
        self.assertEqual(profiles["penjualan"]["type"], "Angka")
        self.assertEqual(profiles["penjualan"]["mean"], 121666.667)
        self.assertEqual(profiles["kategori"]["type"], "Kategori")
        self.assertEqual(profiles["catatan"]["type"], "Teks")
        self.assertEqual(profiles["opsional"]["missing"], 2)
        self.assertEqual(len(data["preview"]), 3)
        self.assertTrue(any("sel kosong" in finding.lower() for finding in data["findings"]))

        report_response = self.client.get(
            f"/api/report/{data['report_id']}?keyword=data"
        )
        self.assertEqual(report_response.status_code, 200)
        workbook = pd.ExcelFile(BytesIO(report_response.data))
        self.assertEqual(
            workbook.sheet_names,
            ["Ringkasan", "Profil Kolom", "Contoh Data"],
        )
        column_report = pd.read_excel(
            BytesIO(report_response.data), sheet_name="Profil Kolom"
        )
        self.assertIn("penjualan", column_report["column"].tolist())

    def test_general_profile_requires_a_tabular_file(self):
        response = self.client.post("/api/profile", data={}, content_type="multipart/form-data")

        self.assertEqual(response.status_code, 400)
        self.assertIn("Pilih file data", response.get_json()["error"])

    def test_analyze_upload_compares_competitors_and_downloads_report(self):
        frame = pd.DataFrame([
            {
                "caption": "Tas wanita murah promo menarik untuk acara santai setiap hari",
                "brand": "Merek A",
            },
            {
                "caption": "Tas wanita harga murah dengan voucher spesial untuk pembeli",
                "brand": "Merek A",
            },
            {
                "caption": "Tas wanita elegan dengan desain minimalis untuk bekerja",
                "brand": "Merek B",
            },
            {
                "caption": "Tas wanita aesthetic dan elegan dengan model simpel",
                "brand": "Merek B",
            },
        ])
        csv_file = BytesIO(frame.to_csv(index=False).encode("utf-8"))
        response = self.client.post(
            "/api/analyze",
            data={
                "keyword": "tas wanita",
                "limit": "100",
                "file": (csv_file, "competitor.csv"),
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 200)
        data = response.get_json()
        self.assertEqual(data["brands"], ["Merek A", "Merek B"])
        self.assertEqual(data["sample_count"], 4)
        self.assertGreater(len(data["comparison"]), 0)
        self.assertEqual(data["group_sizes"], {"Merek A": 2, "Merek B": 2})
        self.assertIn("uncertainty", data["methodology"])
        self.assertIn("Selang Wilson", data["notes"][2])
        self.assertIn("Selang Wilson 95% bawah (%)", data["comparison"][0])
        self.assertIn("Selisih vs Merek A (pp)", data["comparison"][0])

        report_response = self.client.get(
            f"/api/report/{data['report_id']}?keyword=tas%20wanita"
        )
        self.assertEqual(report_response.status_code, 200)
        self.assertEqual(
            report_response.mimetype,
            "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
        report = pd.ExcelFile(BytesIO(report_response.data))
        self.assertIn("Perbandingan Kompetitor", report.sheet_names)
        summary = pd.read_excel(BytesIO(report_response.data), sheet_name="Ringkasan Keputusan")
        self.assertTrue(summary["Indikator"].eq("Selang Wilson").any())

    def test_analyze_requires_two_competitor_labels(self):
        csv_file = BytesIO(
            b"caption,brand\n"
            b"tas wanita murah untuk kebutuhan harian dengan desain sederhana,Merek A\n"
        )
        response = self.client.post(
            "/api/analyze",
            data={
                "keyword": "tas wanita",
                "limit": "100",
                "file": (csv_file, "single.csv"),
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("minimal dua label", response.get_json()["error"])

    def test_analyze_rejects_missing_competitor_column(self):
        csv_file = BytesIO(
            b"caption\n"
            b"tas wanita murah untuk kebutuhan harian dengan desain sederhana\n"
        )
        response = self.client.post(
            "/api/analyze",
            data={
                "keyword": "tas wanita",
                "limit": "100",
                "file": (csv_file, "missing-brand.csv"),
            },
            content_type="multipart/form-data",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("Kolom brand/kompetitor", response.get_json()["error"])


if __name__ == "__main__":
    unittest.main()
