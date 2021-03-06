# -*- coding: utf-8 -*-
# © 2019 Sergio Díaz (<sdimar@yahoo.com>).
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).

from odoo import models, fields, api


class ResPartner(models.Model):
    _inherit = 'res.partner'

    partner_vip = fields.Boolean(
        string="Cliente VIP?")

    partner_plant_hours = fields.Boolean(
        string="Horas en planta")

    reduced_rate = fields.Boolean(
        string="Tarifa reducida")

    @api.model
    def name_search(self, name, args=None, operator='ilike', limit=100):
        args = args or []
        domain = []
        if name:
            domain = ['|', '|',
                      ('name', operator, name),
                      ('city', operator, name),
                      ('ref', '=', name)
                      ]
        partner_ids = self.search(domain + args, limit=limit)
        return partner_ids.name_get()