{
    'name': 'Internal Transfer via Virtual WH',
    'summary': 'Konfirmasi penerimaan produksi melalui lokasi virtual',
    'version': '1.0.0',
    'category': 'Inventory',
    'author': 'Erristhya',
    'license': 'LGPL-3',
    'depends': ['stock', 'vit_validate_int', 'vit_custom_stock_barcode'],
    'data': [
        'security/security.xml', 
        'view/stock_picking_type.xml', 
        'view/stock_picking.xml'
        ],
    'installable': True,
    'application': False,
}
