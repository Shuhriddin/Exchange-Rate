from odoo import models, fields, api

class AccountMove(models.Model):
    _inherit = "account.move"

    apply_manual_exchange = fields.Boolean("Apply Manual Exchange Rate")
    manual_rate = fields.Float("Manual Rate", digits=(12, 4))

    def action_post(self):
        for move in self:
            if move.apply_manual_exchange and move.manual_rate > 0:
                super(AccountMove, move.with_context(
                    manual_currency_rate=move.manual_rate
                )).action_post()
            else:
                super(AccountMove, move).action_post()
        return True
