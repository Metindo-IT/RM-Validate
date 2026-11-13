# Internal Transfer via Virtual WH

Implementasi panduan https://github.com/rahmansaleh7/training_metindo/blob/0906a5fa2d0ce17e35da8a83c0ca2e2a5170b80a/rm_validate/README.md

## Alur

1. Operation pengiriman aktif `Gunakan Konfirmasi Produksi`: WH/Stock -> Virtual.
2. Validate standar tetap menyelesaikan pengiriman menjadi Done. Setelah `_action_done`, status penerimaan menjadi Menunggu Diterima Produksi.
3. Pengguna dengan group `Internal Transfer / Penerima Produksi` menekan Confirm Penerimaan.
4. Sistem membuat transfer kedua ke tujuan produksi, mempertahankan jumlah aktual, UoM, lot/serial, pemilik, dan paket tujuan pengiriman pertama.
5. Setelah transfer kedua Done, dokumen asal menampilkan Confirmed. Status teknis stock.picking.state tetap Done.

## Dependensi kantor menyusul

Atas persetujuan pengguna, addon inti bergantung pada `stock` agar bisa diuji lokal.
Addon terpisah `vit_internal_transfer_metindo` menyatakan dependensi inti + `vit_validate_int` + `vit_custom_stock_barcode`. Pasang bridge hanya setelah source asli dua addon kantor tersedia.
Tidak ada modul pengganti palsu. Context `skip_internal_validation=True` digunakan hanya pada validasi penerimaan kedua setelah pemeriksaan hak akses. Kompatibilitas nyata dengan kode kantor belum diverifikasi.
`validate_produksi` adalah compatibility shim untuk nama latihan lama, bukan implementasi kedua.

## Konfigurasi

- Virtual: Internal, company sama, di bawah view gudang dan bukan anak lokasi stok asal.
- Operation penerimaan: Internal, Virtual -> Produksi, Gunakan Konfirmasi Produksi tidak dicentang.
- Operation pengiriman: Internal, Stock -> Virtual; isi Lokasi Produksi Default dan Operation Type Penerimaan.
- Hanya pengguna produksi diberi group penerima. Tidak membuat user atau mengubah password secara otomatis.
- Pengaturan rute diblokir selama ada penerimaan tertunda.
- Lokasi akhir dapat dipilih di dokumen sebelum pengiriman selesai, harus internal dan company sama.

## Pengaman

- Pemeriksaan group di server, bukan hanya menyembunyikan tombol.
- Status audit tidak bisa ditulis langsung melalui write/create RPC.
- Lock row dokumen pengiriman + unique source pada penerimaan mencegah dokumen penerimaan ganda.
- Stok lot/paket di Virtual harus tersedia dan tidak terikat reservasi lain.
- Perpindahan dan status konfirmasi dalam transaksi/savepoint yang sama; wizard yang belum menyelesaikan transfer tidak dianggap sukses.
- Lot sama persis, tidak menggunakan lot lain hasil FIFO otomatis.
- Dokumen dan baris stok yang sudah diproses pada alur ini tidak boleh diedit/unlock.
- Setelah Confirmed, retur dari dokumen penerimaan; retur pengiriman asal ditolak.
- Jika pengiriman mempunyai retur aktif, konfirmasi ditolak sampai direkonsiliasi.

## Batas lingkup

- Penerimaan penuh atas jumlah yang benar-benar dikirim. Penerimaan sebagian/kerusakan memerlukan wizard terpisah, belum dibuat.
- Pengiriman sebagian melalui backorder standar didukung; hanya bagian Done yang dapat diterima.
- Tidak ada tombol tambahan di antarmuka Barcode; konfirmasi melalui form Inventory backend.
- Tidak ada approval berjenjang, pembatasan per plant, atau reminder aging.
- Valuasi/jurnal belum diuji karena lingkungan inti hanya Inventory; wajib diuji lagi dengan stock_account dan konfigurasi penilaian kantor.
- Pengiriman lama yang selesai sebelum addon terpasang tidak diubah otomatis menjadi menunggu penerimaan (mencegah penerimaan ganda).

## Pengujian

Tes otomatis berada di tests/test_production_confirm.py dan dijalankan pada database terpisah.
Mencakup alur 100 -> 90/10/0 -> 90/0/10, akses, duplicate sequential, lot, pengiriman sebagian, perubahan status langsung, unlock, ordinary transfer, konfigurasi invalid, retur, shortage, dan serial/paket/pemilik.
Tes concurrent dua transaksi dan jurnal valuasi perlu ditambahkan pada lingkungan integrasi kantor; lock dan unique constraint sudah diterapkan.

## Pengembangan

Python: restart service web. XML/schema: upgrade modul di database yang dituju setelah restart.
Folder models/ dipakai konsisten; perbedaan dengan model/ pada README upstream tidak mengubah fungsi Odoo.
