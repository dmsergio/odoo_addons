# -*- coding: utf-8 -*-
# © 2019 Sergio Díaz (<sdimar@yahoo.com>).
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import models, fields, api, _


class SaleOrder(models.Model):

    _inherit = 'sale.order'

    global_price = fields.Float(string="Precio Global")
    picking_pending = fields.Boolean(
        string="Pedidos pendientes",
        states={
            'draft': [('readonly', True)],
            'done': [('readonly', True)],
            'cancel': [('readonly', True)]})
    has_bom = fields.Boolean(compute='_compute_has_bom')
    pendent_to_invoice = fields.Float(
        string='Pendent to invoice',
        compute='_compute_pendent_to_invoice'
    )

    @api.multi
    def _compute_pendent_to_invoice(self):
        product_id = self.env['ir.values'].get_default(
            'sale.config.settings', 'deposit_product_id_setting'
        )
        for sale in self:
            invoice_lines = sale.order_line.mapped('invoice_lines').filtered(
                lambda sol: sol.product_id.id == product_id
            )
            deposit = 0.0
            for line in invoice_lines:
                currency = (
                        line.invoice_id and line.invoice_id.currency_id or None
                )
                price = line.price_unit * (1 - (line.discount or 0.0) / 100.0)
                taxes = line.invoice_line_tax_ids.compute_all(
                    price,
                    currency,
                    line.quantity,
                    product=line.product_id,
                    partner=line.invoice_id.partner_id
                )
                deposit += taxes.get('total_included')
            pendent_to_invoice = sale.amount_total - deposit
            sale.pendent_to_invoice = pendent_to_invoice

    @api.multi
    @api.depends('order_line', 'order_line.mrp_bom_id')
    def _compute_has_bom(self):
        for sale in self:
            if any(sale.order_line.filtered('mrp_bom_id')):
                sale.has_bom = True

    @api.model
    def create(self, values):
        sale_id = super(SaleOrder, self).create(values)
        self.explode_bom()
        sale_id.order_line.recalculate_subtotal()
        self._prepare_compensator_order_line(sale_id)
        return sale_id

    @api.one
    def write(self, values):
        res = super(SaleOrder, self).write(values)
        self.explode_bom()
        if not self.state == "done":
            sale_id = self
            self.order_line.recalculate_subtotal()
            self._prepare_compensator_order_line(sale_id)
        return res

    def _prepare_compensator_order_line(self, sale_id):
        sale_id.ensure_one()
        product_id = \
            self.env.ref("imputations_to_sale.product_template_0000_00_0000")
        product_id = product_id.product_variant_id
        if sale_id.global_price:
            if product_id.id in sale_id.order_line.mapped("product_id").ids:
                line_ids = sale_id.order_line.filtered(
                    lambda x: x.product_id.id != product_id.id)
                total_amount = sum(line_ids.mapped("price_subtotal"))
                amount_compensator = \
                    sale_id.global_price - total_amount
                line_id = sale_id.order_line.filtered(
                    lambda x: x.product_id.id == product_id.id)
                line_id.write({"price_unit": amount_compensator})
            else:
                amount_compensator = \
                    sale_id.global_price - sale_id.amount_untaxed
                values = {
                    'order_id': sale_id.id,
                    'product_id': product_id.id,
                    'price_unit': amount_compensator,
                    'product_uom': product_id.uom_id.id,
                    'product_uom_qty': 1,
                    'name': product_id.name}
                self.env['sale.order.line'].create(values)
        elif sale_id.order_line and sale_id.global_price == 0:
            if product_id.id in sale_id.order_line.mapped("product_id").ids:
                line_id = sale_id.order_line.filtered(
                    lambda x: x.product_id.id == product_id.id)
                line_id.unlink()
        return True


    def get_sale_order(self, lines):
        order_id = False
        if lines:
            order_id = lines.filtered(lambda x: x.order_id)
            order_id = self.search([('id', '=', order_id.order_id.id)], limit=1)
            return order_id

    def explode_bom(self):
        sale_line_obj = self.env["sale.order.line"]
        for line in self.order_line:
            boms = line.product_id.bom_ids.filtered(
                    lambda x: x.type == 'normal')
            if not boms:
                continue
            bom = max(boms, key=lambda x: x['id'])
            for bom_line in bom.bom_line_ids:
                sale_line_obj.create({
                    'product_id': bom_line.product_id.id,
                    'product_uom_qty': bom_line.product_qty *
                                       line.product_uom_qty,
                    'price_unit': bom_line.product_id.lst_price,
                    'mrp_bom_id': bom.id,
                    'purchase_price': bom_line.product_id.standard_price,
                    'name': '[%s] %s' % (bom_line.product_id.default_code or "",
                                         bom_line.product_id.name),
                    'order_id': line.order_id.id})
            line.unlink()

    @api.multi
    def action_cancel(self):
        for record in self:
            if super(SaleOrder, record).action_cancel():
                record.write({'picking_pending': False})
