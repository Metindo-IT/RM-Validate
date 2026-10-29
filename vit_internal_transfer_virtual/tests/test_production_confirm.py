from odoo import Command
from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import TransactionCase, tagged


@tagged('post_install', '-at_install')
class TestProductionConfirm(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.company = cls.env.company
        cls.wh = cls.env['stock.warehouse'].search([('company_id', '=', cls.company.id)], limit=1)
        cls.source = cls.wh.lot_stock_id
        cls.virtual, cls.final = cls.env['stock.location'].create([
            {'name': 'Test Virtual', 'usage': 'internal', 'location_id': cls.wh.view_location_id.id, 'company_id': cls.company.id},
            {'name': 'Test Production', 'usage': 'internal', 'location_id': cls.wh.view_location_id.id, 'company_id': cls.company.id},
        ])
        cls.in_type = cls.env['stock.picking.type'].create({
            'name': 'Test Production Receipt', 'code': 'internal', 'sequence_code': 'TPR',
            'warehouse_id': cls.wh.id, 'default_location_src_id': cls.virtual.id,
            'default_location_dest_id': cls.final.id,
        })
        cls.out_type = cls.env['stock.picking.type'].create({
            'name': 'Test Production Dispatch', 'code': 'internal', 'sequence_code': 'TPD',
            'warehouse_id': cls.wh.id, 'default_location_src_id': cls.source.id,
            'default_location_dest_id': cls.virtual.id, 'use_production_confirm': True,
            'production_location_id': cls.final.id, 'receive_picking_type_id': cls.in_type.id,
        })
        cls.product = cls.env['product.product'].create({
            'name': 'Test Material', 'type': 'consu', 'is_storable': True,
        })
        cls.env['stock.quant']._update_available_quantity(cls.product, cls.source, 100)
        base_groups = [cls.env.ref('base.group_user').id, cls.env.ref('stock.group_stock_user').id]
        cls.sender = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Test Sender', 'login': 'test_virtual_sender',
            'company_id': cls.company.id, 'company_ids': [Command.set([cls.company.id])],
            'group_ids': [Command.set(base_groups)],
        })
        cls.receiver = cls.env['res.users'].with_context(no_reset_password=True).create({
            'name': 'Test Receiver', 'login': 'test_virtual_receiver',
            'company_id': cls.company.id, 'company_ids': [Command.set([cls.company.id])],
            'group_ids': [Command.set(base_groups + [cls.env.ref('vit_internal_transfer_virtual.group_production_receiver').id])],
        })

    def dispatch(self, qty=10, actual=None, product=None, lots=None):
        product = product or self.product
        p = self.env['stock.picking'].create({
            'picking_type_id': self.out_type.id, 'location_id': self.source.id,
            'location_dest_id': self.virtual.id,
            'move_ids': [Command.create({'name': product.name, 'product_id': product.id,
                'product_uom': product.uom_id.id, 'product_uom_qty': qty,
                'location_id': self.source.id, 'location_dest_id': self.virtual.id})],
        })
        p.action_confirm()
        p.action_assign()
        if lots:
            p.move_ids._do_unreserve()
            self.env['stock.move.line'].create([{
                'move_id': p.move_ids.id, 'picking_id': p.id, 'product_id': product.id,
                'product_uom_id': product.uom_id.id, 'location_id': self.source.id,
                'location_dest_id': self.virtual.id, 'lot_id': lot.id, 'quantity': quantity,
                'picked': True,
            } for lot, quantity in lots])
        else:
            p.move_ids.quantity = qty if actual is None else actual
        p.move_ids.picked = True
        p.with_context(skip_backorder=True).button_validate()
        self.assertEqual(p.state, 'done')
        return p

    def qty(self, location, product=None):
        return sum(self.env['stock.quant'].search([
            ('product_id', '=', (product or self.product).id), ('location_id', '=', location.id),
        ]).mapped('quantity'))

    def test_01_full_flow_permissions_and_duplicate(self):
        p = self.dispatch()
        self.assertEqual(p.receive_state, 'to_receive')
        self.assertEqual(p.display_state, 'done')
        self.assertEqual([self.qty(l) for l in (self.source, self.virtual, self.final)], [90, 10, 0])
        with self.assertRaises(AccessError):
            p.with_user(self.sender).action_production_confirm()
        p.with_user(self.receiver).action_production_confirm()
        self.assertEqual(p.state, 'done')
        self.assertEqual(p.display_state, 'received')
        self.assertEqual(p.received_by_id, self.receiver)
        self.assertEqual(p.receive_picking_id.state, 'done')
        self.assertEqual([self.qty(l) for l in (self.source, self.virtual, self.final)], [90, 0, 10])
        with self.assertRaises(UserError):
            p.with_user(self.receiver).action_production_confirm()
        self.assertEqual(self.env['stock.picking'].search_count([('production_source_picking_id', '=', p.id)]), 1)

    def test_02_exact_lots(self):
        product = self.env['product.product'].create({'name': 'Lot Material', 'type': 'consu', 'is_storable': True, 'tracking': 'lot'})
        lot_a, lot_b, unrelated = self.env['stock.lot'].create([
            {'name': name, 'product_id': product.id, 'company_id': self.company.id}
            for name in ('A', 'B', 'UNRELATED')
        ])
        self.env['stock.quant']._update_available_quantity(product, self.source, 4, lot_id=lot_a)
        self.env['stock.quant']._update_available_quantity(product, self.source, 6, lot_id=lot_b)
        self.env['stock.quant']._update_available_quantity(product, self.virtual, 50, lot_id=unrelated)
        p = self.dispatch(product=product, lots=[(lot_a, 4), (lot_b, 6)])
        p.with_user(self.receiver).action_production_confirm()
        actual = {(ml.lot_id.id, ml.quantity) for ml in p.receive_picking_id.move_line_ids}
        self.assertEqual(actual, {(lot_a.id, 4), (lot_b.id, 6)})
        self.assertEqual(self.qty(self.virtual, product), 50)

    def test_03_partial_dispatch(self):
        p = self.dispatch(qty=10, actual=6)
        backorder = self.env['stock.picking'].search([('backorder_id', '=', p.id)])
        self.assertTrue(backorder)
        self.assertFalse(backorder.receive_state)
        self.assertNotEqual(backorder.state, 'done')
        p.with_user(self.receiver).action_production_confirm()
        self.assertEqual(self.qty(self.final), 6)

    def test_04_no_direct_status_write_or_unlock(self):
        p = self.dispatch()
        with self.assertRaises(AccessError):
            p.write({'receive_state': 'received'})
        with self.assertRaises(UserError):
            p.action_toggle_is_locked()
        with self.assertRaises(UserError):
            p.move_line_ids.write({'quantity': 12})
        with self.assertRaises(UserError):
            self.out_type.write({'use_production_confirm': False})

    def test_05_ordinary_internal_unchanged(self):
        p = self.env['stock.picking'].create({
            'picking_type_id': self.in_type.id, 'location_id': self.source.id,
            'location_dest_id': self.final.id,
            'move_ids': [Command.create({'name': 'Ordinary', 'product_id': self.product.id,
                'product_uom': self.product.uom_id.id, 'product_uom_qty': 2,
                'location_id': self.source.id, 'location_dest_id': self.final.id})],
        })
        p.button_validate()
        self.assertEqual(p.state, 'done')
        self.assertFalse(p.receive_state)
        self.assertEqual(p.display_state, 'done')

    def test_06_invalid_route(self):
        with self.assertRaises(ValidationError), self.env.cr.savepoint():
            self.out_type.write({'production_location_id': self.virtual.id})

    def test_07_return_from_receipt_only(self):
        p = self.dispatch()
        p.with_user(self.receiver).action_production_confirm()
        wizard = self.env['stock.return.picking'].with_context(active_id=p.id, active_ids=p.ids, active_model='stock.picking').create({})
        with self.assertRaises(UserError):
            wizard._create_return()
        receipt = p.receive_picking_id
        wizard2 = self.env['stock.return.picking'].with_context(active_id=receipt.id, active_ids=receipt.ids, active_model='stock.picking').create({})
        wizard2.product_return_moves.write({'quantity': 10})
        returned = wizard2._create_return()
        self.assertTrue(returned)

    def test_08_shortage_rolls_back(self):
        p = self.dispatch()
        self.env['stock.quant']._update_available_quantity(self.product, self.virtual, -5)
        with self.assertRaises(UserError):
            p.with_user(self.receiver).action_production_confirm()
        self.assertEqual(p.receive_state, 'to_receive')
        self.assertFalse(p.receive_picking_id)
        self.assertFalse(self.env['stock.picking'].search([('production_source_picking_id', '=', p.id)]))

    def test_09_package_owner_and_serial_preserved(self):
        product = self.env['product.product'].create({'name': 'Serial Material', 'type': 'consu', 'is_storable': True, 'tracking': 'serial'})
        lot = self.env['stock.lot'].create({'name': 'SERIAL-001', 'product_id': product.id, 'company_id': self.company.id})
        owner = self.env['res.partner'].create({'name': 'Material Owner'})
        source_package = self.env['stock.quant.package'].create({'name': 'SOURCE-PACK'})
        result_package = self.env['stock.quant.package'].create({'name': 'REPACKED'})
        self.env['stock.quant']._update_available_quantity(product, self.source, 1, lot_id=lot, package_id=source_package, owner_id=owner)
        p = self.env['stock.picking'].create({
            'picking_type_id': self.out_type.id, 'location_id': self.source.id, 'location_dest_id': self.virtual.id,
            'move_ids': [Command.create({'name': product.name, 'product_id': product.id,
                'product_uom': product.uom_id.id, 'product_uom_qty': 1,
                'location_id': self.source.id, 'location_dest_id': self.virtual.id})],
        })
        p.action_confirm()
        p.move_ids._do_unreserve()
        self.env['stock.move.line'].create({
            'move_id': p.move_ids.id, 'picking_id': p.id, 'product_id': product.id,
            'product_uom_id': product.uom_id.id, 'location_id': self.source.id,
            'location_dest_id': self.virtual.id, 'lot_id': lot.id, 'quantity': 1,
            'package_id': source_package.id, 'result_package_id': result_package.id,
            'owner_id': owner.id, 'picked': True,
        })
        p.move_ids.picked = True
        p.button_validate()
        p.with_user(self.receiver).action_production_confirm()
        line = p.receive_picking_id.move_line_ids
        self.assertEqual(line.lot_id, lot)
        self.assertEqual(line.package_id, result_package)
        self.assertEqual(line.result_package_id, result_package)
        self.assertEqual(line.owner_id, owner)
        self.assertEqual(line.quantity, 1)
