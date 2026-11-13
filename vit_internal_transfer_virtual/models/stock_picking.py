from collections import defaultdict

from odoo import api, fields, models, _
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tools.float_utils import float_compare


class StockPicking(models.Model):
    _inherit = 'stock.picking'

    use_production_confirm = fields.Boolean(related='picking_type_id.use_production_confirm')
    final_location_dest_id = fields.Many2one(
        'stock.location', 'Tujuan Akhir Produksi', check_company=True,
        compute='_compute_final_location', store=True, readonly=False,
        domain="[('usage', '=', 'internal')]",
    )
    receive_state = fields.Selection([
        ('to_receive', 'Menunggu Diterima Produksi'), ('received', 'Confirmed'),
    ], string='Status Penerimaan', copy=False, readonly=True, tracking=True, index=True)
    receive_picking_id = fields.Many2one('stock.picking', 'Dokumen Penerimaan', copy=False, readonly=True)
    production_source_picking_id = fields.Many2one(
        'stock.picking', 'Pengiriman Asal Produksi', copy=False, readonly=True, index=True,
    )
    received_by_id = fields.Many2one('res.users', 'Diterima Oleh', copy=False, readonly=True)
    received_date = fields.Datetime('Waktu Diterima', copy=False, readonly=True)
    display_state = fields.Selection([
        ('draft', 'Draft'), ('waiting', 'Waiting Another Operation'),
        ('confirmed', 'Waiting'), ('assigned', 'Ready'), ('done', 'Done'),
        ('cancel', 'Cancelled'), ('received', 'Confirmed'),
    ], compute='_compute_display_state', string='Tahap Produksi')

    _unique_production_receipt = models.Constraint(
        'UNIQUE(production_source_picking_id)', 'Pengiriman ini sudah mempunyai dokumen penerimaan.',
    )

    @api.depends('picking_type_id', 'picking_type_id.production_location_id')
    def _compute_final_location(self):
        for picking in self:
            picking.final_location_dest_id = picking.picking_type_id.production_location_id

    @api.depends('state', 'receive_state', 'use_production_confirm')
    def _compute_display_state(self):
        for picking in self:
            picking.display_state = (
                'received' if picking.use_production_confirm and picking.state == 'done'
                and picking.receive_state == 'received' else picking.state
            )

    def write(self, vals):
        protected = {'receive_state', 'receive_picking_id', 'production_source_picking_id',
                     'received_by_id', 'received_date'}
        if protected.intersection(vals):
            raise AccessError(_('Status penerimaan hanya boleh diubah melalui Confirm Penerimaan.'))
        if {'location_id', 'location_dest_id', 'final_location_dest_id', 'picking_type_id',
            'move_ids', 'move_line_ids', 'company_id'}.intersection(vals):
            self._check_production_editable()
        return super().write(vals)

    @api.model_create_multi
    def create(self, vals_list):
        for vals in vals_list:
            if any(vals.get(key) for key in ('receive_state', 'receive_picking_id',
                   'production_source_picking_id', 'received_by_id', 'received_date')):
                raise AccessError(_('Data konfirmasi tidak dapat diisi langsung.'))
        return super().create(vals_list)

    def _check_production_editable(self):
        if any(p.state == 'done' and (p.receive_state or p.production_source_picking_id) for p in self):
            raise UserError(_('Transfer produksi yang sudah selesai tidak boleh diubah. Gunakan prosedur retur.'))

    def action_toggle_is_locked(self):
        self._check_production_editable()
        return super().action_toggle_is_locked()

    def _check_production_route(self):
        for picking in self.filtered('use_production_confirm'):
            picking.picking_type_id._check_production_configuration()
            final = picking.final_location_dest_id
            if (not final or final.usage != 'internal' or final.company_id != picking.company_id
                    or final in (picking.location_id, picking.location_dest_id)):
                raise ValidationError(_('Pilih lokasi akhir produksi Internal dalam company yang sama.'))
            if picking.location_dest_id != picking.picking_type_id.default_location_dest_id:
                raise ValidationError(_('Tujuan pengiriman harus lokasi Virtual yang dikonfigurasi.'))
            if any(m.location_dest_id != picking.location_dest_id for m in picking.move_ids
                   if m.state != 'cancel') or any(
                    ml.location_dest_id != picking.location_dest_id for ml in picking.move_line_ids
                    if ml.quantity > 0):
                raise ValidationError(_('Semua baris pengiriman harus menuju lokasi Virtual yang sama.'))

    def _action_done(self):
        self._check_production_route()
        res = super()._action_done()
        pending = self.filtered(lambda p: p.use_production_confirm and p.state == 'done' and not p.receive_state)
        if pending:
            super(StockPicking, pending).write({'receive_state': 'to_receive'})
        return res

    def action_production_confirm(self):
        self.ensure_one()
        self.check_access('write')
        if not self.env.user.has_group('vit_internal_transfer_virtual.group_production_receiver'):
            raise AccessError(_('Hanya Penerima Produksi yang boleh melakukan konfirmasi.'))
        # Serialize concurrent requests; a second transaction cannot create a second receipt.
        self.flush_recordset()
        self.env.cr.execute('SELECT id FROM stock_picking WHERE id = %s FOR UPDATE', [self.id])
        self.invalidate_recordset()
        if (not self.use_production_confirm or self.state != 'done'
                or self.receive_state != 'to_receive' or self.receive_picking_id):
            raise UserError(_('Pengiriman belum selesai atau sudah dikonfirmasi.'))
        self._check_production_route()
        source_lines = self.move_line_ids.filtered(lambda ml: ml.state == 'done' and ml.quantity > 0)
        if not source_lines:
            raise UserError(_('Tidak ada kuantitas yang dapat diterima.'))
        if self.move_ids.returned_move_ids.filtered(lambda m: m.state != 'cancel'):
            raise UserError(_('Pengiriman mempunyai retur. Selesaikan rekonsiliasi sebelum konfirmasi produksi.'))

        # Keep the actual destination package, lot, owner and UoM from the completed shipment.
        quantities = defaultdict(float)
        for ml in source_lines:
            key = (ml.product_id.id, ml.lot_id.id, ml.result_package_id.id, ml.owner_id.id)
            quantities[key] += ml.product_uom_id._compute_quantity(ml.quantity, ml.product_id.uom_id)
        for (product_id, lot_id, package_id, owner_id), qty in quantities.items():
            product = self.env['product.product'].browse(product_id)
            if not product.is_storable:
                continue
            quants = self.env['stock.quant'].search([
                ('product_id', '=', product_id), ('location_id', '=', self.location_dest_id.id),
                ('lot_id', '=', lot_id), ('package_id', '=', package_id), ('owner_id', '=', owner_id),
            ])
            available = sum(q.quantity - q.reserved_quantity for q in quants)
            if float_compare(available, qty, precision_rounding=product.uom_id.rounding) < 0:
                raise UserError(_('Stok lot/paket di Virtual tidak cukup atau sudah direservasi: %s', product.display_name))

        with self.env.cr.savepoint():
            receipt = self.env['stock.picking'].create({
                'picking_type_id': self.picking_type_id.receive_picking_type_id.id,
                'company_id': self.company_id.id,
                'location_id': self.location_dest_id.id,
                'location_dest_id': self.final_location_dest_id.id,
                'origin': self.name,
            })
            super(StockPicking, receipt).write({'production_source_picking_id': self.id})
            pairs = []
            for original in self.move_ids.filtered(lambda m: m.state == 'done'):
                lines = source_lines.filtered(lambda ml: ml.move_id == original)
                if not lines:
                    continue
                actual = sum(ml.product_uom_id._compute_quantity(ml.quantity, original.product_uom) for ml in lines)
                move = self.env['stock.move'].create({
                    'name': original.name, 'product_id': original.product_id.id,
                    'product_uom': original.product_uom.id, 'product_uom_qty': actual,
                    'picking_id': receipt.id, 'company_id': self.company_id.id,
                    'location_id': self.location_dest_id.id,
                    'location_dest_id': self.final_location_dest_id.id,
                })
                pairs.append((move, lines))
            # Preserve one-to-one source move mapping instead of merging identical products.
            receipt.move_ids._action_confirm(merge=False)
            receipt.move_ids._do_unreserve()
            receipt.move_line_ids.unlink()
            for move, lines in pairs:
                self.env['stock.move.line'].create([{
                    'move_id': move.id, 'picking_id': receipt.id,
                    'company_id': self.company_id.id, 'product_id': ml.product_id.id,
                    'product_uom_id': ml.product_uom_id.id, 'quantity': ml.quantity,
                    'location_id': self.location_dest_id.id,
                    'location_dest_id': self.final_location_dest_id.id,
                    'lot_id': ml.lot_id.id, 'package_id': ml.result_package_id.id,
                    'result_package_id': ml.result_package_id.id,
                    'owner_id': ml.owner_id.id, 'picked': True,
                } for ml in lines])
                move.picked = True
            receipt.with_context(skip_internal_validation=True, skip_backorder=True).button_validate()
            if receipt.state != 'done':
                raise UserError(_('Penerimaan belum selesai. Konfirmasi dibatalkan tanpa mengubah status.'))
            super(StockPicking, self).write({
                'receive_state': 'received', 'receive_picking_id': receipt.id,
                'received_by_id': self.env.user.id, 'received_date': fields.Datetime.now(),
            })
            self._message_log(body=_('Penerimaan produksi selesai melalui %s.', receipt.name))
            receipt._message_log(body=_('Penerimaan dari pengiriman %s.', self.name))
        return self.action_view_production_receipt()

    def action_view_production_receipt(self):
        self.ensure_one()
        return {'type': 'ir.actions.act_window', 'name': _('Penerimaan Produksi'),
                'res_model': 'stock.picking', 'res_id': self.receive_picking_id.id,
                'view_mode': 'form', 'target': 'current'}
