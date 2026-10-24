# Market Insight — Analisis Data

Aplikasi web lokal dengan portofolio Deni Somantri sebagai halaman utama dan workbench analisis interaktif. Workbench meringkas data tabel CSV/Excel atau membandingkan tema caption kompetitor; tidak memerlukan coding dan hasil dapat diunduh sebagai Excel.

## Menjalankan di Windows

1. Klik dua kali `Jalankan_Aplikasi.bat`.
2. Saat pertama kali dijalankan, launcher memasang dependensi dari `requirements-app.txt` bila ada dependensi aplikasi yang belum tersedia.
3. Browser akan membuka portofolio di `http://127.0.0.1:5000`.
4. Pilih **Coba aplikasi analisis** atau **Buka aplikasi analisis** untuk masuk ke workbench di `/app`.
5. Pilih **Analisis data umum** untuk file tabel atau **Bandingkan caption kompetitor** untuk riset caption.
6. Unggah file CSV/Excel, lalu ikuti ringkasan yang ditampilkan.
7. Kembali ke portofolio melalui tautan di bagian atas workbench.

Server hanya terikat ke `127.0.0.1` dan tidak dibagikan ke jaringan lokal.

## Deploy untuk pengujian publik

Portfolio statis sudah dapat ditayangkan di Netlify. Untuk menjalankan workbench analisis, host backend Flask secara terpisah di PythonAnywhere:

1. Unggah atau clone repository ke `/home/deni999/mysite` pada PythonAnywhere. Pastikan `app.py`, `scraper_market_intelligence.py`, `tabular_analysis.py`, folder `templates`, dan `requirements-app.txt` ada di sana.
2. Pasang dependensi proyek di virtualenv PythonAnywhere dengan `pip install -r /home/deni999/mysite/requirements-app.txt`.
3. Buka file WSGI `/var/www/deni999_pythonanywhere_com_wsgi.py` dari tab **Web** PythonAnywhere, lalu salin isi file `deni999_pythonanywhere_com_wsgi.py` dari repository ini ke sana. File dalam repository adalah salinan konfigurasi; mengunggahnya ke GitHub tidak otomatis mengubah file WSGI di server.
4. Atur virtualenv aplikasi di tab **Web**, lalu klik **Reload**.
5. Setelah backend tersedia di `https://deni999.pythonanywhere.com`, ubah tujuan proxy pada `netlify.toml` dari host Render menjadi domain PythonAnywhere, lalu commit dan push perubahan tersebut agar Netlify melakukan deploy ulang.

File unggahan diproses oleh server dan tidak disimpan permanen oleh aplikasi. Karena situs publik tidak memerlukan login, jangan unggah data pribadi atau rahasia. Lihat batasan penggunaan paket hosting sebelum membagikan aplikasi untuk pengujian.

## Analisis data umum

Gunakan file CSV atau Excel yang tersusun sebagai tabel: setiap baris adalah satu catatan dan setiap kolom memiliki judul. Contohnya data penjualan, survei, stok barang, kampanye pemasaran, atau pencatatan operasional. Kolom tidak perlu bernama khusus.

Analisis merangkum:

- Jumlah baris/kolom dan sel kosong.
- Kolom angka: nilai terkecil, terbesar, rata-rata, dan median.
- Kolom kategori: nilai yang paling sering muncul.
- Kolom tanggal: rentang tanggal.
- Kolom teks: panjang rata-rata dan beberapa contoh.
- Contoh hingga 20 baris data untuk memeriksa apakah file terbaca benar.

Maksimal file 10 MB, 50.000 baris yang dianalisis, dan 60 kolom. Untuk Excel dengan banyak sheet, aplikasi menganalisis sheet pertama yang berisi data. Format selain tabel CSV/Excel (misalnya PDF, gambar, atau audio) belum didukung. Ringkasan ini bersifat deskriptif; tidak otomatis menemukan sebab-akibat atau memprediksi hasil bisnis.

Contoh file bisa diunduh dari tombol **Lihat contoh data penjualan** di aplikasi.

## Perbandingan caption kompetitor

Pilih mode **Bandingkan caption kompetitor**. File perlu memiliki dua kolom:

- `caption`: teks caption yang ingin dibandingkan.
- `brand`: nama merek pemilik caption.

Contoh:

```csv
caption,brand
"Tas ringan untuk sehari-hari",Merek A
"Tas kerja dengan banyak ruang",Merek B
```

CSV atau workbook Excel multi-sheet dapat digunakan. Nama kolom lain yang umum juga dikenali, misalnya `merek`, `kompetitor`, `teks`, atau `deskripsi`. Data perlu memiliki minimal dua merek dan caption yang sesuai dengan topik untuk tiap merek. Maksimum unggahan 10 MB; file hanya diproses sementara di memori.

Persentase caption hanya menggambarkan data sampel yang diunggah, bukan pangsa pasar atau preferensi semua pelanggan. Klasifikasi tema menggunakan pencocokan kata kunci sederhana. Validasi sampel dan hasil sebelum mengambil keputusan.

## Tes

Jalankan semua pengujian:

```powershell
python -m unittest -v test_scraper_market_intelligence.py test_app.py
```
