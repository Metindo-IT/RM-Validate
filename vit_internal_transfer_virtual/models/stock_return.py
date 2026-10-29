from odoo import models, _
from odoo.exceptions import UserError


class StockReturnPicking(models.TransientModel):
    _inherit = 'stock.return.picking'

    def _create_return(self):
        if self.picking_id.receive_state == 'received':
            raise UserError(_('Buat retur dari dokumen penerimaan produksi, bukan pengiriman asal.'))
        return super()._create_return()
