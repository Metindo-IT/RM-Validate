from odoo import api, fields, models, _
from odoo.exceptions import ValidationError, UserError


class StockPickingType(models.Model):
    _inherit = 'stock.picking.type'

    use_production_confirm = fields.Boolean('Gunakan Konfirmasi Produksi')
    production_location_id = fields.Many2one(
        'stock.location', 'Lokasi Produksi Default', check_company=True,
        domain="[('usage', '=', 'internal')]",
    )
    receive_picking_type_id = fields.Many2one(
        'stock.picking.type', 'Operation Type Penerimaan', check_company=True,
        domain="[('code', '=', 'internal'), ('use_production_confirm', '=', False)]",
    )

    @api.constrains('use_production_confirm', 'production_location_id',
                    'receive_picking_type_id', 'default_location_src_id',
                    'default_location_dest_id', 'company_id', 'code')
    def _check_production_configuration(self):
        for op in self.filtered('use_production_confirm'):
            source, virtual, final = (op.default_location_src_id,
                                      op.default_location_dest_id,
                                      op.production_location_id)
            receiver = op.receive_picking_type_id
            if op.code != 'internal' or not all((source, virtual, final, receiver)):
                raise ValidationError(_('Lengkapi lokasi dan operation type penerimaan untuk transfer internal.'))
            if len({source.id, virtual.id, final.id}) != 3:
                raise ValidationError(_('Lokasi asal, virtual, dan produksi harus berbeda.'))
            if any(loc.usage != 'internal' or loc.company_id != op.company_id
                   for loc in (source, virtual, final)):
                raise ValidationError(_('Semua lokasi harus Internal dan dimiliki company yang sama.'))
            if virtual.scrap_location or self.env['stock.location'].search_count([
                ('id', '=', virtual.id), ('id', 'child_of', source.id),
            ]):
                raise ValidationError(_('Lokasi virtual tidak boleh Scrap atau berada di bawah lokasi stok asal.'))
            if (receiver.code != 'internal' or receiver.use_production_confirm
                    or receiver.company_id != op.company_id
                    or receiver.default_location_src_id != virtual
                    or receiver.default_location_dest_id != final):
                raise ValidationError(_('Operation penerimaan harus Internal: Virtual ke Produksi, tanpa konfirmasi berulang.'))

    def write(self, vals):
        keys = {'use_production_confirm', 'production_location_id', 'receive_picking_type_id',
                'default_location_src_id', 'default_location_dest_id', 'company_id', 'code'}
        if keys.intersection(vals):
            routes = self | self.search([('receive_picking_type_id', 'in', self.ids)])
            if self.env['stock.picking'].search_count([
                ('picking_type_id', 'in', routes.ids), ('receive_state', '=', 'to_receive'),
            ]):
                raise UserError(_('Selesaikan penerimaan yang tertunda sebelum mengubah rute.'))
        res = super().write(vals)
        if keys.intersection(vals):
            self.search([('receive_picking_type_id', 'in', self.ids)])._check_production_configuration()
        return res
