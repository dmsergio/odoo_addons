# -*- coding: utf-8 -*-
# © 2019 Sergio Díaz (<sdimar@yahoo.com>).
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import models, fields, api
import datetime


class SaleOrderLine(models.Model):

    _inherit = 'sale.order.line'

    order_date = fields.Date(
        string="Fecha",
        default=datetime.datetime.now().date())

    operator_product_id = fields.Many2one(
        comodel_name="product.template",
        string="Operario")

    type_working_day = fields.Selection(
        [("regular", "Normal"),
         ("night", "Nocturna"),
         ("holiday", "Festiva"),
         ("night_holiday", "Nocturna/Festiva")],
        string="Tipo de jornada",
        default="regular")

    sale_line_plant_hours = fields.Boolean(
        string="Horas en planta")
    mrp_bom_id = fields.Many2one(
        comodel_name='mrp.bom',
        string='Lista de materiales',
    )
    fixed_price = fields.Boolean(
        string='Fixed price',
        help='Check if you do not want to recompute subtotal price.'
    )

    def recalculate_subtotal(self):
        # OPERARIOS
        operator_category_ids = self.get_operator_category()
        operator_product_ids = self.env["product.template"].search([
            ("categ_id", "in", operator_category_ids)]).mapped(
            "product_variant_id")

        # PUESTO DE TRABAJO
        machine_product_ids = self.get_machine_category()
        machine_product_ids = self.env["product.template"].search([
            ("categ_id", "in", machine_product_ids)]).mapped(
            "product_variant_id")

        product_ids = operator_product_ids.ids + machine_product_ids.ids
        product_ids.append(self.env.ref(
            "imputations_to_sale.product_template_0000_00_0000").\
                           product_variant_id.id)
        Pricelist = self.env['mejisa.product.pricelist']
        for record in self:
            partner = record.order_id.partner_id
            if (
                    record.product_id.id not in product_ids
                    and not (
                        record.fixed_price or record.product_id.fixed_price
            )):
                subtotal = record.purchase_price * record.product_uom_qty
                dom = [
                    ('amount_1', '<=', subtotal),
                    ('amount_2', '>=', subtotal),
                ]
                pricelist = Pricelist.search(dom ,limit=1)
                if pricelist:
                    increase = (
                        partner.reduced_rate and pricelist.decrease or
                        pricelist.increase
                    )
                    record.price_unit = (
                        record.purchase_price
                        + (record.purchase_price * increase) / 100
                    )
        return True

    def get_parent_operator_category(self):
        return self.env["product.category"].browse(769).id

    def get_operator_category(self):
        parent_category_id = self.get_parent_operator_category()
        return self.env["product.category"].search([
            ("parent_id", "=", parent_category_id)]).ids

    def get_machine_category(self):
        return self.env["product.category"].browse(770).ids

    @api.multi
    @api.onchange('product_id')
    def product_id_change(self):
        res = super(SaleOrderLine, self).product_id_change()
        if self.product_id:
            self.sale_line_plant_hours = \
                self.order_id.partner_id.partner_plant_hours
        return res

    def unlink_line(self):
        self.ensure_one()
        context = self.env.context.copy()
        context.update({
            'default_product_id': self.operator_product_id.id,
            'default_order_date': self.order_date
        })
        if not context.get('default_product_id'):
            context['default_sale_id'] = self.order_id.id
        self.unlink()
        vals = {
            'type': 'ir.actions.act_window',
            'res_model': 'impute.hours.wiz'
            if context.get('default_product_id') else 'impute.material.wiz',
            'context': context,
            'view_type': 'form',
            'view_mode': 'form',
            'target': 'inline'
        }
        return vals