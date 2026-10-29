# RM Validate — Transfer melalui Virtual Warehouse

Addon `vit_internal_transfer_virtual` menambahkan konfirmasi penerimaan produksi pada internal transfer Odoo. Saat gudang menekan Validate, barang berpindah ke lokasi Virtual. Setelah penerima produksi menekan Confirm, sistem memindahkan barang ke lokasi produksi dan menampilkan tahap Confirmed pada dokumen asal.

## Isi repo

- `vit_internal_transfer_virtual/`: kode addon, hak akses, tampilan, dan tes otomatis.
- [Panduan konfigurasi dan batasan](vit_internal_transfer_virtual/README.md).

## Menjalankan

1. Gunakan Odoo yang sesuai. Kode ini sudah diuji di saas-18.2; kompatibilitas versi kantor perlu diperiksa.
2. Letakkan folder addon pada addons path server, restart Odoo, lalu perbarui daftar aplikasi dan install **Internal Transfer via Virtual WH** pada database tujuan.
3. Buat lokasi Virtual bertipe Internal serta operation type penerimaan Virtual → Produksi.
4. Pada operation type pengiriman Gudang → Virtual, aktifkan **Gunakan Konfirmasi Produksi**, pilih lokasi akhir produksi dan operation type penerimaannya.
5. Berikan grup **Penerima Produksi** kepada user penerima.

Nama VWHOUT/VWHIN dan lokasi gudang adalah konfigurasi database, bukan data yang otomatis dibuat oleh addon. User, password, transaksi latihan, serta backup database tidak disertakan.

## Validasi yang sudah dilakukan

Sembilan skenario tes otomatis berhasil pada database latihan terpisah. Simulasi lokal terbaru juga berhasil: stok 10/0/0 menjadi 9/1/0 setelah Validate, lalu 9/0/1 setelah Confirm. Konfirmasi ulang ditolak.

Integrasi dengan `vit_validate_int` dan `vit_custom_stock_barcode` kantor belum diverifikasi. Bridge opsional `vit_internal_transfer_metindo` dan modul latihan lama tidak disertakan dalam pengiriman ini. Uji valuasi dan konkurensi dua transaksi masih diperlukan sebelum pemakaian kantor.
