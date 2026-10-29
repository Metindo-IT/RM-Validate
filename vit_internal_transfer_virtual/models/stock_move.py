from odoo import api, models


class StockMove(models.Model):
    _inherit = 'stock.move'

    def write(self, vals):
        if {'quantity', 'product_uom_qty', 'product_id', 'product_uom', 'location_id',
            'location_dest_id', 'move_line_ids', 'picking_id', 'state'}.intersection(vals):
            self.picking_id._check_production_editable()
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        self.env['stock.picking'].browse([v['picking_id'] for v in vals_list if v.get('picking_id')])._check_production_editable()
        return super().create(vals_list)

    def unlink(self):
        self.picking_id._check_production_editable()
        return super().unlink()


class StockMoveLine(models.Model):
    _inherit = 'stock.move.line'

    def write(self, vals):
        if {'quantity', 'product_id', 'product_uom_id', 'location_id', 'location_dest_id',
            'lot_id', 'lot_name', 'package_id', 'result_package_id', 'owner_id',
            'move_id', 'picking_id'}.intersection(vals):
            self.picking_id._check_production_editable()
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        pickings = self.env['stock.picking'].browse([v['picking_id'] for v in vals_list if v.get('picking_id')])
        pickings |= self.env['stock.move'].browse([v['move_id'] for v in vals_list if v.get('move_id')]).picking_id
        pickings._check_production_editable()
        return super().create(vals_list)

    def unlink(self):
        self.picking_id._check_production_editable()
        return super().unlink()
